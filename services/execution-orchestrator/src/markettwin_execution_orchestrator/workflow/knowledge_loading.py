"""Run-start source-knowledge loading and the mid-run open tool.

Doc 33 section 3.6: a run's pinned source knowledge (the snapshot's
``source_knowledge`` block, written at creation) is loaded at plan
time — directly attached files whole, attached collections selected
from their manifests (BM25 shortlist, character n-gram fallback,
then the ask door's ``select_knowledge_files`` as the escalation
when both scorers come up empty) and packed at section granularity
— under one per-run token budget, with every omission named.
Loaded files are fenced reference data: they inform, they never
verdict (section 3.7).

The read seam is control-api's internal knowledge-files endpoint;
this service holds no S3 credentials. Every load — direct, selected,
mid-run — writes a ``knowledge.file.opened`` run event, so a run's
knowledge use is fully auditable afterwards. Nothing here raises
into a run: reference data is never worth failing a test run over.
"""

import math
import os
import re
import unicodedata
from collections import Counter
from hashlib import sha256

import httpx
from markettwin_database.models import TestRun

from markettwin_execution_orchestrator.models import ask
from markettwin_execution_orchestrator.persistence.run_event_repository import (
    RunEventRepository,
)

try:  # The Step 0 contract estimator, once landed.
    from markettwin_shared.knowledge_markdown import estimate_tokens
except ImportError:  # pragma: no cover - pre-Step-0 trees only.

    def estimate_tokens(text: str) -> int:
        """The contract estimator: ceil(len/4)."""

        return -(-len(text) // 4)


# Doc 33 section 3.6 point 3: one per-run source-knowledge token
# budget [J]. Direct files (the owner's explicit choice) spend
# first; selected files spend in chosen order.
SOURCE_KNOWLEDGE_TOKEN_BUDGET = 24000
SHORTLIST_LIMIT = 8
# SKR step 2 (research R2): collection packing holds this much of
# the budget back so a mid-run open_knowledge_file can still be
# honoured; no single collection file may take more than a third
# of the budget either. Both are carve-outs of a large budget —
# a budget at or under the reserve is spent as before.
MID_RUN_RESERVE_TOKENS = 2000


def _budget_limit() -> int:
    raw = os.getenv("MARKETTWIN_SOURCE_KNOWLEDGE_TOKEN_BUDGET", "")
    try:
        value = int(raw)
    except ValueError:
        return SOURCE_KNOWLEDGE_TOKEN_BUDGET
    return value if value > 0 else SOURCE_KNOWLEDGE_TOKEN_BUDGET


class KnowledgeFilesClient:
    """The internal control-api read seam (section 3.6). Any failure
    returns None — an unavailable file is an omission, never a crash."""

    def __init__(self, *, base_url: str | None = None, secret: str | None = None):
        self._base = (
            base_url
            or os.getenv("MARKETTWIN_CONTROL_API_URL", "http://127.0.0.1:8000")
        ).rstrip("/")
        if secret is None:
            secret = os.getenv("KNOWLEDGE_INTERNAL_SECRET")
        self._headers = (
            {"Authorization": f"Bearer {secret}"} if secret else {}
        )

    async def _get(self, path: str, params: dict | None = None) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.get(
                    f"{self._base}{path}", headers=self._headers, params=params,
                )
            if response.status_code != 200:
                return None
            body = response.json()
        except Exception:
            return None
        return body if isinstance(body, dict) else None

    async def fetch_file_content(self, file_id: str) -> dict | None:
        return await self._get(f"/internal/v1/knowledge-files/{file_id}/content")

    async def fetch_collection_manifest(
        self, entry_id: str, version: int,
    ) -> dict | None:
        return await self._get(
            f"/internal/v1/knowledge-files/collections/{entry_id}/manifest",
            params={"version": version},
        )


_STOPWORDS = frozenset({
    "the", "and", "for", "are", "with", "this", "that", "from",
    "into", "your", "you", "can", "how", "what", "when", "does",
    "did", "will", "would", "there", "their", "them", "then",
})


def _tokens(text: str) -> list[str]:
    """NFKC + casefolded word tokens (runs of Unicode letters and
    numbers), stopwords removed. The stopwords stay [J]: at
    tens-of-files scale IDF alone gives a shared "and" a positive
    weight, and the wrong file would score above zero."""

    tokens: list[str] = []
    current: list[str] = []
    for char in unicodedata.normalize("NFKC", text).casefold():
        if unicodedata.category(char)[0] in "LN":
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return [t for t in tokens if len(t) >= 2 and t not in _STOPWORDS]


def _bm25_scores(query: str, surfaces: list[str]) -> list[float]:
    """Okapi BM25 of the query against each surface (stdlib only).
    IDF uses the non-negative form, safe on a two-document corpus."""

    docs = [Counter(_tokens(surface)) for surface in surfaces]
    query_terms = set(_tokens(query))
    if not docs or not query_terms:
        return [0.0] * len(surfaces)
    count = len(docs)
    avg_len = sum(sum(doc.values()) for doc in docs) / count or 1.0
    scores: list[float] = []
    for doc in docs:
        doc_len = sum(doc.values())
        score = 0.0
        for term in query_terms:
            df = sum(1 for other in docs if term in other)
            if not df or term not in doc:
                continue
            idf = math.log(1.0 + (count - df + 0.5) / (df + 0.5))
            tf = doc[term]
            score += idf * (tf * 2.5) / (tf + 1.5 * (0.25 + 0.75 * doc_len / avg_len))
        scores.append(score)
    return scores


def _ngram_scores(query: str, surfaces: list[str]) -> list[float]:
    """Character 3-5-gram cosine between the query and each
    surface — the fallback for unsegmented scripts, morphology and
    word variants that whole tokens miss. A surface needs at least
    two distinct shared grams to score at all [J]: a single shared
    character run is noise (a paraphrase brief shares exactly one
    stray gram with an unrelated file)."""

    def grams(text: str) -> Counter:
        flat = re.sub(
            r"\s+", " ", unicodedata.normalize("NFKC", text).casefold(),
        )
        counts: Counter = Counter()
        for size in (3, 4, 5):
            for i in range(len(flat) - size + 1):
                counts[flat[i:i + size]] += 1
        return counts

    query_grams = grams(query)
    query_norm = math.sqrt(sum(v * v for v in query_grams.values()))
    scores: list[float] = []
    for surface in surfaces:
        surface_grams = grams(surface)
        shared = query_grams.keys() & surface_grams.keys()
        if len(shared) < 2 or not query_norm:
            scores.append(0.0)
            continue
        dot = sum(query_grams[g] * surface_grams[g] for g in shared)
        norm = math.sqrt(sum(v * v for v in surface_grams.values()))
        scores.append(dot / (query_norm * norm) if norm else 0.0)
    return scores


def _surface(entry: dict) -> str:
    return " ".join([
        str(entry.get("title") or ""),
        str(entry.get("description") or ""),
        " ".join(
            str(h) for h in entry.get("section_headings") or []
            if isinstance(h, str)
        ),
    ])


def _rank_files(
    manifest_files: list[dict], *, selection_text: str,
    limit: int = SHORTLIST_LIMIT,
) -> list[dict]:
    """Rank a collection's files against the selection text: BM25
    first; the character n-gram fallback only when BM25 finds
    nothing. An empty result means both scorers came up empty —
    the caller escalates to the ask door."""

    entries = [
        entry for entry in manifest_files
        if isinstance(entry, dict) and entry.get("file_id")
    ]
    if not entries:
        return []
    surfaces = [_surface(entry) for entry in entries]
    for scorer in (_bm25_scores, _ngram_scores):
        scores = scorer(selection_text, surfaces)
        ranked = sorted(
            (
                (-score, index, entry)
                for index, (entry, score) in enumerate(
                    zip(entries, scores, strict=True)
                )
                if score > 0
            ),
            key=lambda item: (item[0], item[1]),
        )
        if ranked:
            return [entry for _, _, entry in ranked[:limit]]
    return []


def shortlist_files(
    manifest_files: list[dict], *, selection_text: str, limit: int = SHORTLIST_LIMIT,
) -> list[dict]:
    """The deterministic shortlist (section 3.6 step 2a), SKR
    step 2: BM25 over each file's title, description and section
    headings, with the character n-gram fallback behind it.
    Zero-score files are not shortlisted; ties keep manifest
    order."""

    return _rank_files(
        manifest_files, selection_text=selection_text, limit=limit,
    )


def _content_tokens(content: dict, text: str) -> int:
    known = content.get("token_count")
    if isinstance(known, int) and not isinstance(known, bool) and known > 0:
        return known
    return estimate_tokens(text)


def _split_sections(text: str, title: str) -> list[dict]:
    """Split a rendered knowledge file into its sections (SKR
    step 2, research R2): frontmatter is dropped, H2 headings
    bound the sections, and anything before the first H2 (the H1
    and any intro) is a section of its own, headed by the H1 text
    or the file title. A section is the atomic packing unit —
    it is loaded whole or not at all."""

    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                lines = lines[index + 1:]
                break
    sections: list[dict] = []
    heading: str | None = None
    body: list[str] = []

    def flush() -> None:
        content = "\n".join(body).strip()
        if not content:
            return
        if heading is None:
            first = content.split("\n", 1)[0]
            name = first[2:].strip() if first.startswith("# ") else title
            sections.append({"heading": name or title, "text": content})
        else:
            sections.append({
                "heading": heading, "text": f"## {heading}\n\n{content}",
            })

    for line in lines:
        if line.startswith("## "):
            flush()
            heading = line[3:].strip()
            body = []
        else:
            body.append(line)
    flush()
    return sections


def _pack_sections(
    title: str, text: str, *, selection_text: str, cap: int, pool: int,
) -> tuple[str, int, int] | None:
    """Pack one collection file's relevant sections under the
    per-file cap and the remaining collection pool. Sections are
    ranked by BM25 within the file (document order when none
    score) and admitted greedily — never truncated. Returns
    (packed text, tokens, skipped tokens) or None when no section
    fits; skipped tokens counts relevant sections that did not
    fit, for the budget omission."""

    sections = _split_sections(text, title)
    if not sections:
        return None
    scores = _bm25_scores(
        selection_text, [f"{s['heading']} {s['text']}" for s in sections],
    )
    positives = sorted(
        (
            (-score, index)
            for index, score in enumerate(scores) if score > 0
        ),
        key=lambda item: (item[0], item[1]),
    )
    order = [index for _, index in positives] or list(range(len(sections)))
    relevant = {index for _, index in positives}
    chunks: list[str] = []
    used = 0
    skipped = 0
    for index in order:
        section = sections[index]
        if section["heading"] == title:
            prefix = f"{title}\n"
        else:
            prefix = f"{title} › {section['heading']}\n"
        chunk = prefix + section["text"]
        tokens = estimate_tokens(chunk)
        if used + tokens <= cap and used + tokens <= pool:
            chunks.append(chunk)
            used += tokens
        elif index in relevant:
            skipped += estimate_tokens(section["text"])
    if not chunks:
        return None
    packed = "\n\n".join(chunks)
    return packed, estimate_tokens(packed), skipped


async def _record_opened(session, run_id, entry: dict, *, via: str) -> None:
    await RunEventRepository(session).create(
        test_run_id=run_id, event_type="knowledge.file.opened",
        journey_id=None, execution_id=None,
        payload={"file_id": entry["file_id"], "slug": entry["slug"], "via": via},
    )


async def load_source_knowledge(
    *, request, session, selection_text: str, client=None,
) -> tuple[dict, list[dict]] | None:
    """Plan-time loading for one run. Returns (plan section,
    omissions) or None when the run pinned no source knowledge.
    Omissions are named, never silent: [{slug, reason}] with reason
    budget | unavailable | integrity | selection_unavailable, plus
    token_count whenever a count is known (fetched content or the
    manifest entry)."""

    pin = getattr(request, "source_knowledge", None)
    if not isinstance(pin, dict):
        return None
    client = client or KnowledgeFilesClient()
    budget = _budget_limit()
    used = 0
    loaded: list[dict] = []
    omitted: list[dict] = []
    carried: list[dict] = []
    # Collection content packs under a ceiling that holds the
    # mid-run reserve back; direct pins are the owner's explicit
    # choice and may spend the whole budget.
    collection_ceiling = (
        budget - MID_RUN_RESERVE_TOKENS
        if budget > MID_RUN_RESERVE_TOKENS else budget
    )
    per_file_cap = max(1, budget // 3)

    def omit(slug: str, reason: str, token_count=None) -> None:
        entry = {"slug": slug, "reason": reason}
        if isinstance(token_count, int) and not isinstance(token_count, bool):
            entry["token_count"] = token_count
        omitted.append(entry)

    async def try_load(file_id: str, expected_sha: str, slug: str, via: str) -> None:
        nonlocal used
        content = await client.fetch_file_content(file_id)
        if content is None or not isinstance(content.get("text"), str):
            omit(slug, "unavailable")
            return
        text = content["text"]
        tokens = _content_tokens(content, text)
        if sha256(text.encode("utf-8")).hexdigest() != expected_sha:
            omit(slug, "integrity", tokens)
            return
        if used + tokens > budget:
            omit(slug, "budget", tokens)
            return
        entry = {
            "file_id": file_id,
            "entry_id": str(content.get("entry_id") or ""),
            "slug": slug,
            "title": str(content.get("title") or slug),
            "description": str(content.get("description") or ""),
            "text": text,
            "token_count": tokens,
            "via": via,
        }
        loaded.append(entry)
        used += tokens
        await _record_opened(session, request.run_id, entry, via=via)

    async def pack_load(entry: dict) -> None:
        """Load one collection file by packing its relevant
        sections (SKR step 2): the whole file is fetched and
        hash-verified, then its sections are admitted atomically
        under the per-file cap and the collection ceiling."""

        nonlocal used
        file_id = str(entry["file_id"])
        if any(item["file_id"] == file_id for item in loaded):
            return
        slug = str(entry.get("slug") or "")
        manifest_tokens = entry.get("token_count")
        content = await client.fetch_file_content(file_id)
        if content is None or not isinstance(content.get("text"), str):
            omit(slug, "unavailable", manifest_tokens)
            return
        text = content["text"]
        if sha256(text.encode("utf-8")).hexdigest() != str(
            entry.get("sha256") or ""
        ):
            omit(slug, "integrity", _content_tokens(content, text))
            return
        title = str(content.get("title") or entry.get("title") or slug)
        packed = _pack_sections(
            title, text, selection_text=selection_text,
            cap=per_file_cap, pool=collection_ceiling - used,
        )
        if packed is None:
            omit(slug, "budget", manifest_tokens)
            return
        packed_text, tokens, skipped = packed
        loaded_entry = {
            "file_id": file_id,
            "entry_id": str(content.get("entry_id") or ""),
            "slug": slug,
            "title": title,
            "description": str(
                content.get("description") or entry.get("description") or ""
            ),
            "text": packed_text,
            "token_count": tokens,
            "via": "selection",
        }
        loaded.append(loaded_entry)
        used += tokens
        await _record_opened(session, request.run_id, loaded_entry, via="selection")
        if skipped:
            omit(slug, "budget", skipped)

    for pinned in pin.get("files") or []:
        await try_load(
            str(pinned["file_id"]), str(pinned["sha256"]),
            str(pinned["slug"]), "direct",
        )

    for collection in pin.get("collections") or []:
        entry_id = str(collection["entry_id"])
        version = collection.get("version")
        manifest_files: list[dict] = []
        if isinstance(version, int) and not isinstance(version, bool):
            manifest = await client.fetch_collection_manifest(entry_id, version)
            if manifest is not None and isinstance(manifest.get("files"), list):
                manifest_files = [
                    entry for entry in manifest["files"] if isinstance(entry, dict)
                ]
        valid = [
            entry for entry in manifest_files if entry.get("file_id")
        ]
        by_id = {str(entry["file_id"]): entry for entry in valid}
        recorded = collection.get("selection_order")
        selection_order: list[str] | None = None
        if isinstance(recorded, list) and recorded:
            # A resumed run replays the door's recorded order
            # verbatim — no scorer and no door call (SKR step 2).
            order = [
                by_id[file_id] for file_id in recorded
                if isinstance(file_id, str) and file_id in by_id
            ]
            selection_order = [str(entry["file_id"]) for entry in order]
        else:
            order = _rank_files(valid, selection_text=selection_text)
        if valid and not order:
            # Both scorers came up empty (a paraphrased or
            # cross-lingual brief): escalate to the ask door over
            # the full manifest — one bounded call, only here.
            candidates = [
                {
                    "file_id": str(entry["file_id"]),
                    "title": str(entry.get("title") or ""),
                    "description": str(entry.get("description") or ""),
                }
                for entry in valid
            ]
            try:
                chosen = await ask.select_knowledge_files(
                    candidates=candidates, brief=request.study_brief,
                )
            except Exception:
                chosen = None
            if chosen:
                order = [
                    by_id[file_id] for file_id in chosen
                    if isinstance(file_id, str) and file_id in by_id
                ]
                selection_order = [str(entry["file_id"]) for entry in order]
            if not order:
                for entry in valid:
                    omit(
                        str(entry.get("slug") or ""),
                        "selection_unavailable", entry.get("token_count"),
                    )
        carried_entry = {
            "entry_id": entry_id,
            "manifest_object_key": str(collection.get("manifest_object_key") or ""),
            "version": version,
            "manifest": manifest_files,
        }
        if selection_order is not None:
            carried_entry["selection_order"] = selection_order
        carried.append(carried_entry)
        for entry in order:
            await pack_load(entry)

    section = {
        "files": loaded,
        "collections": carried,
        "budget": {"limit": budget, "used_tokens": used},
    }
    return section, omitted


async def open_knowledge_file(
    *, session, run_id, plan: dict, file_id: str, client=None,
) -> dict:
    """The mid-run harness tool (doc 33 section 3.6 point 5): open
    one more file from an attached collection's manifest. Refusals
    come back with their reason; nothing raises. A successful open
    appends to the plan's loaded set, writes the opened event, and
    persists the plan back into the run snapshot so a resumed run
    keeps the file."""

    refused = {"status": "refused", "file_id": file_id}
    section = plan.get("source_knowledge") if isinstance(plan, dict) else None
    if not isinstance(section, dict):
        return {**refused, "reason": "no_source_knowledge"}
    loaded = section.get("files")
    if not isinstance(loaded, list):
        loaded = section["files"] = []
    if any(
        isinstance(entry, dict) and entry.get("file_id") == file_id
        for entry in loaded
    ):
        return {"status": "already_loaded", "file_id": file_id}
    manifest_entry = None
    for collection in section.get("collections") or []:
        if not isinstance(collection, dict):
            continue
        for entry in collection.get("manifest") or []:
            if isinstance(entry, dict) and entry.get("file_id") == file_id:
                manifest_entry = entry
                break
        if manifest_entry is not None:
            break
    if manifest_entry is None:
        return {**refused, "reason": "not_in_attached_collections"}
    budget = section.get("budget")
    budget = budget if isinstance(budget, dict) else {}
    limit = budget.get("limit")
    limit = limit if isinstance(limit, int) else _budget_limit()
    used = budget.get("used_tokens")
    used = used if isinstance(used, int) else 0
    known_tokens = manifest_entry.get("token_count")
    if (
        isinstance(known_tokens, int) and not isinstance(known_tokens, bool)
        and used + known_tokens > limit
    ):
        return {**refused, "reason": "budget"}
    client = client or KnowledgeFilesClient()
    content = await client.fetch_file_content(file_id)
    if content is None or not isinstance(content.get("text"), str):
        return {**refused, "reason": "unavailable"}
    text = content["text"]
    if sha256(text.encode("utf-8")).hexdigest() != str(
        manifest_entry.get("sha256") or ""
    ):
        return {**refused, "reason": "integrity"}
    tokens = _content_tokens(content, text)
    if used + tokens > limit:
        return {**refused, "reason": "budget"}
    entry = {
        "file_id": file_id,
        "entry_id": str(content.get("entry_id") or ""),
        "slug": str(manifest_entry.get("slug") or content.get("slug") or ""),
        "title": str(content.get("title") or manifest_entry.get("title") or ""),
        "description": str(
            content.get("description") or manifest_entry.get("description") or ""
        ),
        "text": text,
        "token_count": tokens,
        "via": "midrun",
    }
    loaded.append(entry)
    section["budget"] = {"limit": limit, "used_tokens": used + tokens}
    await _record_opened(session, run_id, entry, via="midrun")
    run = await session.get(TestRun, run_id)
    if run is not None:
        snapshot = dict(run.configuration_snapshot or {})
        snapshot["app_plan"] = plan
        run.configuration_snapshot = snapshot
        await session.flush()
    return {"status": "opened", "file": {"file_id": file_id, "slug": entry["slug"]}}

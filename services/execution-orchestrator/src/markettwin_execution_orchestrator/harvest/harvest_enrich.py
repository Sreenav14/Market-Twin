"""Template enrichment (doc 16 section 5.6).

This is the ONE module in the harvest that may call a model — the
boundary is AST-pinned by test T-JB8. Pages are grouped into template
groups; the model drafts a PURPOSE for each group from the group's
exemplar, and nothing else: no expectations, no journeys from thin
air, no navigation facts. Every draft is written with oracle source
'model-draft' (it can never silently upgrade), the spend is recorded
through the repository's sink immediately per call, and the caps are
recorded on the map row BEFORE the first call is made.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

HARVEST_MODEL_CALL_CAP = 300  # [J] doc 16 section 13, provisional (decision D1)
HARVEST_MODEL_TOKEN_CAP = 1_000_000  # [J] doc 16 section 13, provisional
ENRICH_ARIA_MAX_CHARS = 12000  # [J] doc 16 section 13
ENRICH_MAX_TOKENS = 512

_SYSTEM_PROMPT = (
    "You describe one page template of a web application for a testing "
    "map. Answer with JSON only, in exactly this shape: "
    '{"purpose": string, "actions": [string], "journey_name": string|null}. '
    "purpose: one sentence, at most 300 characters, saying what this "
    "page is for. actions: at most 12 short names of the main things a "
    "user can do on this page. journey_name: if this page is the end "
    "of a user journey (for example a demo, signup, or contact page), "
    "a short name for that journey, otherwise null. Describe only "
    "what the evidence shows; never invent features."
)


@dataclass(frozen=True)
class Exemplar:
    """What the prompt is built from: one page standing for its group."""

    url: str
    route_pattern: str
    title: str
    element_names: list[str]
    form_labels: list[str]
    aria_excerpt: str


class EnrichmentDoor(Protocol):
    """The ask door, narrowed to what enrichment needs (faked in tests)."""

    async def draft(self, *, system: str, user: str) -> Any: ...


class TokenAccountant(Protocol):
    """Charges one call the way the ask door charges it: input tokens
    counted, output tokens reserved at the cap."""

    def __call__(self, *, system: str, user: str) -> int: ...


class ModelApiDoor:
    """Production door: the Model API through the one typed ask door."""

    async def draft(self, *, system: str, user: str) -> Any:
        from markettwin_execution_orchestrator.models.ask import _model_json

        return await _model_json(system, user, max_tokens=ENRICH_MAX_TOKENS)


def default_accountant(*, system: str, user: str) -> int:
    import litellm

    from markettwin_execution_orchestrator.models.ask import (
        resolve_model_runtime_configuration,
    )

    configuration = resolve_model_runtime_configuration(
        max_tokens=ENRICH_MAX_TOKENS
    )
    input_tokens = litellm.token_counter(  # pyright: ignore[reportUnknownMemberType]
        model=configuration.model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return int(input_tokens) + ENRICH_MAX_TOKENS


def group_pages(
    entries: list[tuple[Any, str | None]],
) -> dict[str, list[Any]]:
    """Group visited pages into template groups (doc 16 section 5.6).

    ``entries`` are (page, exemplar dom_structure_hash) pairs. Pages
    group by route pattern; groups whose exemplars share a structure
    hash merge, and the merged group's key is the lexicographically
    smallest member pattern.
    """
    by_pattern: dict[str, list[Any]] = {}
    exemplar_hash: dict[str, str | None] = {}
    for page, dom_hash in entries:
        by_pattern.setdefault(page.route_pattern, []).append(page)
        exemplar_hash.setdefault(page.route_pattern, dom_hash)
    patterns = sorted(by_pattern)
    parent = {pattern: pattern for pattern in patterns}

    def find(pattern: str) -> str:
        while parent[pattern] != pattern:
            parent[pattern] = parent[parent[pattern]]
            pattern = parent[pattern]
        return pattern

    by_hash: dict[str, str] = {}
    for pattern in patterns:
        dom_hash = exemplar_hash[pattern]
        if dom_hash is None:
            continue
        if dom_hash in by_hash:
            root_a, root_b = find(pattern), find(by_hash[dom_hash])
            if root_a != root_b:
                parent[max(root_a, root_b)] = min(root_a, root_b)
        else:
            by_hash[dom_hash] = pattern
    groups: dict[str, list[Any]] = {}
    for pattern in patterns:
        groups.setdefault(find(pattern), []).extend(by_pattern[pattern])
    return groups


def build_prompt(exemplar: Exemplar) -> tuple[str, str]:
    user = (
        f"Page: {exemplar.url}\n"
        f"Route pattern: {exemplar.route_pattern}\n"
        f"Title: {exemplar.title}\n"
        f"Elements: {', '.join(exemplar.element_names[:80])}\n"
        f"Form fields: {', '.join(exemplar.form_labels[:40])}\n"
        f"Accessibility excerpt:\n{exemplar.aria_excerpt[:ENRICH_ARIA_MAX_CHARS]}"
    )
    return _SYSTEM_PROMPT, user


def validate_draft(raw: Any) -> dict[str, Any] | None:
    """The section 5.6 output contract; None means malformed."""
    if not isinstance(raw, dict):
        return None
    purpose = raw.get("purpose")
    if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 300:
        return None
    actions = raw.get("actions")
    if not isinstance(actions, list) or len(actions) > 12:
        return None
    if not all(isinstance(action, str) for action in actions):
        return None
    journey_name = raw.get("journey_name")
    if journey_name is not None and (
        not isinstance(journey_name, str) or len(journey_name) > 80
    ):
        return None
    return {
        "purpose": purpose.strip(),
        "actions": list(actions),
        "journey_name": journey_name,
    }


@dataclass
class EnrichResult:
    groups_total: int = 0
    enriched_groups: int = 0
    unenriched: list[dict[str, str]] = field(default_factory=list)
    spend_calls: int = 0
    spend_tokens: int = 0
    cap_reached: str | None = None  # 'model_calls' | 'model_tokens'


async def enrich_map(
    *,
    repository: Any,
    app_map: Any,
    groups: dict[str, list[Any]],
    exemplars: dict[str, Exemplar],
    door: EnrichmentDoor,
    accountant: TokenAccountant,
) -> EnrichResult:
    """Draft purposes for every template group, inside the caps.

    The caps land on the map row before the first call (T-EN5); spend
    is written immediately per call through the repository sink, so a
    crash mid-enrichment leaves the spend truthful. A group the model
    cannot describe stays unenriched WITH its reason — never silently
    skipped, never retried past one malformed-output retry.
    """
    result = EnrichResult(groups_total=len(groups))
    await repository.record_mapping_budgets(
        app_map.id,
        calls_cap=HARVEST_MODEL_CALL_CAP,
        tokens_cap=HARVEST_MODEL_TOKEN_CAP,
    )
    fresh = await repository.get_map(app_map.id)
    spend_calls = (fresh.mapping_spend_calls or 0) if fresh is not None else 0
    spend_tokens = (fresh.mapping_spend_tokens or 0) if fresh is not None else 0
    group_enrichment: dict[str, object] = dict(
        (app_map.harvest_metrics or {}).get("group_enrichment") or {}
    )
    unenriched_keys: list[str] = []

    async def save_progress() -> None:
        await repository.save_harvest_metrics(
            app_map.id,
            {
                "group_enrichment": dict(group_enrichment),
                "template_groups": {
                    "groups": len(groups),
                    "unenriched_groups": list(unenriched_keys),
                },
            },
        )

    for group_key in sorted(groups):
        if spend_calls >= HARVEST_MODEL_CALL_CAP:
            result.cap_reached = "model_calls"
            unenriched_keys.append(group_key)
            result.unenriched.append({"group": group_key, "reason": "cap"})
            continue
        if spend_tokens >= HARVEST_MODEL_TOKEN_CAP:
            result.cap_reached = "model_tokens"
            unenriched_keys.append(group_key)
            result.unenriched.append({"group": group_key, "reason": "cap"})
            continue
        exemplar = exemplars.get(group_key)
        if exemplar is None:
            unenriched_keys.append(group_key)
            result.unenriched.append(
                {"group": group_key, "reason": "no_exemplar"}
            )
            continue
        system, user = build_prompt(exemplar)
        draft: dict[str, Any] | None = None
        door_failed = False
        cap_exhausted = False
        for _attempt in range(2):  # one retry on malformed output
            tokens = accountant(system=system, user=user)
            if spend_calls >= HARVEST_MODEL_CALL_CAP or spend_tokens + tokens > HARVEST_MODEL_TOKEN_CAP:
                result.cap_reached = (
                    "model_calls" if spend_calls >= HARVEST_MODEL_CALL_CAP else "model_tokens"
                )
                cap_exhausted = True
                break
            # Reserve before dispatch: errors and process death must not erase attempted spend.
            spend_calls, spend_tokens = await repository.record_enrichment_spend(
                app_map.id, calls_delta=1, tokens_delta=tokens,
            )
            try:
                raw = await door.draft(system=system, user=user)
            except Exception:
                door_failed = True
                break
            draft = validate_draft(raw)
            if draft is not None:
                break
        if door_failed:
            unenriched_keys.append(group_key)
            result.unenriched.append(
                {"group": group_key, "reason": "door_error"}
            )
            # The model service is failing; stop rather than mark
            # every remaining group with the same error one by one.
            for remaining in sorted(groups):
                if remaining > group_key and remaining not in unenriched_keys:
                    unenriched_keys.append(remaining)
                    result.unenriched.append(
                        {"group": remaining, "reason": "door_error"}
                    )
            await save_progress()
            break
        if draft is None:
            unenriched_keys.append(group_key)
            result.unenriched.append(
                {"group": group_key, "reason": "cap" if cap_exhausted else "invalid_output"}
            )
            await save_progress()
            continue
        group_enrichment[group_key] = draft
        for page in groups[group_key]:
            await repository.set_page_purpose(
                page.id,
                purpose=str(draft["purpose"]),
                purpose_source="model-draft",
                template_group=group_key,
            )
        result.enriched_groups += 1
        await save_progress()
    result.spend_calls = spend_calls
    result.spend_tokens = spend_tokens
    return result

"""Doc 33 step 6 wiring: GroundingRepository attaches approved files.

The production repository must return approved entries WITH their
knowledge files attached (slug + rendered Markdown read through the
injected reader), or production grounding authors no documentation
candidates. Rows are real model instances; the fake session applies
the statement's own equality criteria on the queried entity's table,
so the repository's approval/status filters do the filtering. Only
the S3 read is faked (the injected reader).
"""

import asyncio
from uuid import uuid4

from markettwin_database.models.knowledge import (
    ApplicationKnowledgeEntry,
    BlueprintVersion,
    IngestionEntry,
    KnowledgeFile,
)

from markettwin_execution_orchestrator.expectations.expectations_repository import (
    GroundingRepository,
)
from markettwin_execution_orchestrator.expectations.grounding import (
    extract_candidates,
)

PRICING_MD = """# Pricing

## Plans
The Pro plan costs $50 per month.
"""

REFUNDS_MD = """# Refunds

## Window
Refunds are available within 30 days of purchase.
"""


class AsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


def _equality_clauses(stmt, entity):
    where = getattr(stmt, "whereclause", None)
    if where is None:
        return []
    clauses = list(where.clauses) if hasattr(where, "clauses") else [where]
    found = []
    for clause in clauses:
        left = getattr(clause, "left", None)
        right = getattr(clause, "right", None)
        if left is None or right is None:
            continue
        if getattr(left, "table", None) is not entity.__table__:
            continue
        if hasattr(right, "value"):
            found.append((left.key, right.value))
    return found


class RowSession:
    def __init__(self, rows_by_entity, by_id):
        self._rows = rows_by_entity
        self._by_id = by_id

    async def get(self, model, primary_key):
        return self._by_id.get(primary_key)

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        rows = list(self._rows.get(entity, []))
        for column, value in _equality_clauses(stmt, entity):
            rows = [row for row in rows if getattr(row, column, None) == value]
        return _Result(rows)


class TextReader:
    def __init__(self, texts):
        self.texts = texts
        self.seen: list[str] = []

    async def __call__(self, object_key: str) -> str:
        self.seen.append(object_key)
        return self.texts[object_key]


def _entry(workspace_id, blueprint_id):
    return IngestionEntry(
        id=uuid4(), workspace_id=workspace_id, blueprint_id=blueprint_id,
        asset_version_id=uuid4(), preview={},
    )


def _version(entry, status):
    return BlueprintVersion(
        id=entry.id, workspace_id=entry.workspace_id,
        blueprint_id=entry.blueprint_id, version_number=1, status=status,
        created_by_user_id=uuid4(),
    )


def _file(entry, slug, version, status, key):
    return KnowledgeFile(
        id=uuid4(), workspace_id=entry.workspace_id,
        ingestion_entry_id=entry.id, slug=slug, title=slug.title(),
        description=f"About {slug}.", object_key=key, sha256="a" * 64,
        token_count=10, version=version, status=status,
    )


def _world(version_status="approved"):
    workspace_id, blueprint_id, application_id = uuid4(), uuid4(), uuid4()
    entry = _entry(workspace_id, blueprint_id)
    other = _entry(workspace_id, uuid4())
    prefix = f"knowledge/{workspace_id}/{entry.id}/files"
    keys = {
        "pricing": f"{prefix}/v2/pricing.md",
        "refunds": f"{prefix}/v2/refunds.md",
    }
    rows = {
        ApplicationKnowledgeEntry: [
            ApplicationKnowledgeEntry(
                workspace_id=workspace_id, application_id=application_id,
                ingestion_entry_id=entry.id, attached_by_user_id=uuid4(),
            ),
        ],
        BlueprintVersion: [_version(entry, version_status), _version(other, "approved")],
        KnowledgeFile: [
            _file(entry, "pricing", 2, "approved", keys["pricing"]),
            _file(entry, "pricing", 1, "superseded", f"{prefix}/v1/pricing.md"),
            _file(entry, "refunds", 2, "approved", keys["refunds"]),
            _file(entry, "billing", 2, "generated", f"{prefix}/v2/billing.md"),
            _file(other, "pricing", 1, "approved", "knowledge/other/pricing.md"),
        ],
    }
    session = RowSession(rows, {entry.id: entry, other.id: other})
    texts = {keys["pricing"]: PRICING_MD, keys["refunds"]: REFUNDS_MD}
    return application_id, entry, session, texts, keys


def test_load_approved_entries_attaches_approved_files() -> None:
    application_id, entry, session, texts, keys = _world()
    reader = TextReader(texts)
    repository = GroundingRepository(
        lambda: AsyncContext(session), knowledge_text=reader,
    )
    entries = asyncio.run(repository.load_approved_entries(application_id))
    assert entries == [entry]
    assert entry.knowledge_files == [
        {"slug": "pricing", "content": PRICING_MD},
        {"slug": "refunds", "content": REFUNDS_MD},
    ]
    # Only the two approved, current files were read, in slug order;
    # the superseded, generated, and other-entry objects were not.
    assert reader.seen == [keys["pricing"], keys["refunds"]]
    # End to end: Stream D's reader turns the attachment into candidates.
    candidates = extract_candidates(entries)
    assert [(c.name, c.source_ref) for c in candidates] == [
        ("Plans", f"{entry.id}:pricing:Plans"),
        ("Window", f"{entry.id}:refunds:Window"),
    ]


def test_unapproved_entry_returns_nothing_and_reads_nothing() -> None:
    application_id, _entry_row, session, texts, _keys = _world(version_status="draft")
    reader = TextReader(texts)
    repository = GroundingRepository(
        lambda: AsyncContext(session), knowledge_text=reader,
    )
    assert asyncio.run(repository.load_approved_entries(application_id)) == []
    assert reader.seen == []


def test_without_a_reader_entries_load_bare_as_before() -> None:
    application_id, entry, session, _texts, _keys = _world()
    repository = GroundingRepository(lambda: AsyncContext(session))
    entries = asyncio.run(repository.load_approved_entries(application_id))
    assert entries == [entry]
    assert getattr(entry, "knowledge_files", None) is None

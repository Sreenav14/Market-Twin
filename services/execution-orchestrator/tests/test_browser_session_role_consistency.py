"""Code-vs-schema consistency for browser session roles (D-LIVE-1).

MT-000153 died live because harness code persisted session_role='worker'
while ck_browser_sessions_session_role_allowed only allowed the P2-era
set (room | proof | persona | legacy); the test fakes never enforced
the database constraint. These tests pin the two sides together: every
session_role literal the orchestrator persists must be in the model's
allowed set, and the newest migration defining the constraint must
declare the same set as the model — so the next new role breaks CI
instead of a live run.
"""

import re
from pathlib import Path

from sqlalchemy import UniqueConstraint

from markettwin_execution_orchestrator.persistence.models import BrowserSession

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "markettwin_execution_orchestrator"
)
VERSIONS_DIR = REPO_ROOT / "database" / "migrations" / "versions"
CONSTRAINT_NAME = "ck_browser_sessions_session_role_allowed"
_ROLE_LITERAL = re.compile(r"""session_role\s*(?::\s*str)?\s*=\s*"([a-z_]+)\"""")
_IN_SET = re.compile(r"session_role IN \(([^)]*)\)")


def _model_allowed_roles() -> set[str]:
    for constraint in BrowserSession.__table__.constraints:
        if constraint.name == CONSTRAINT_NAME:
            match = _IN_SET.search(str(constraint.sqltext))
            assert match is not None
            return set(re.findall(r"'([a-z_]+)'", match.group(1)))
    raise AssertionError(f"{CONSTRAINT_NAME} not declared on the model")


def _persisted_roles() -> set[str]:
    roles: set[str] = set()
    for path in SRC_ROOT.rglob("*.py"):
        roles.update(_ROLE_LITERAL.findall(path.read_text(encoding="utf-8")))
    return roles


def test_persisted_session_roles_are_allowed_by_the_schema() -> None:
    persisted = _persisted_roles()
    # The scan must actually find the lane role that killed MT-000153.
    assert "worker" in persisted
    assert persisted <= _model_allowed_roles()


def test_newest_migration_declares_the_model_role_set() -> None:
    revisions: dict[str, tuple[str | None, str]] = {}
    for path in VERSIONS_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        revision = re.search(
            r"^revision(?:\s*:\s*str)?\s*=\s*[\"']([^\"']+)[\"']", source, re.M
        )
        down = re.search(
            r"^down_revision(?:\s*:[^=]+)?\s*=\s*[\"']([^\"']+)[\"']", source, re.M
        )
        if revision:
            revisions[revision.group(1)] = (
                down.group(1) if down else None,
                source,
            )
    children = {down for down, _ in revisions.values() if down}
    heads = [revision for revision in revisions if revision not in children]
    assert len(heads) == 1
    # Walk from the head towards the root; the first migration whose
    # upgrade() defines the constraint is the one the live DB follows.
    current: str | None = heads[0]
    while current is not None:
        down, source = revisions[current]
        if CONSTRAINT_NAME in source and "def upgrade" in source:
            upgrade = source.split("def upgrade", 1)[1].split(
                "def downgrade", 1
            )[0]
            match = _IN_SET.search(upgrade)
            if match:
                migrated = set(re.findall(r"'([a-z_]+)'", match.group(1)))
                assert migrated == _model_allowed_roles()
                return
        current = down
    raise AssertionError("no migration defines the constraint")


EXECUTION_UNIQUE = "uq_browser_sessions_execution_id"


def test_model_allows_sibling_sessions_per_execution() -> None:
    # D-LIVE-1 layer 2 (MT-000155): the Room row and every S2 lane row
    # share the inventory execution, so a single-column unique on
    # execution_id makes the first lane INSERT impossible. The model
    # must not re-declare it; the composite (execution_id, id) unique
    # and the one-open-Room partial index are the invariants that stay.
    singles = [
        constraint
        for constraint in BrowserSession.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and [column.name for column in constraint.columns] == ["execution_id"]
    ]
    assert singles == []


def test_newest_migration_drops_the_execution_unique() -> None:
    # Walk the chain from the head; the first migration whose upgrade()
    # mentions the stale unique must drop it, not recreate it.
    revisions: dict[str, tuple[str | None, str]] = {}
    for path in VERSIONS_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        revision = re.search(
            r"^revision(?:\s*:\s*str)?\s*=\s*[\"']([^\"']+)[\"']", source, re.M
        )
        down = re.search(
            r"^down_revision(?:\s*:[^=]+)?\s*=\s*[\"']([^\"']+)[\"']", source, re.M
        )
        if revision:
            revisions[revision.group(1)] = (
                down.group(1) if down else None,
                source,
            )
    children = {down for down, _ in revisions.values() if down}
    heads = [revision for revision in revisions if revision not in children]
    assert len(heads) == 1
    current: str | None = heads[0]
    while current is not None:
        down, source = revisions[current]
        if EXECUTION_UNIQUE in source and "def upgrade" in source:
            upgrade = source.split("def upgrade", 1)[1].split(
                "def downgrade", 1
            )[0]
            if EXECUTION_UNIQUE in upgrade:
                assert "drop_constraint" in upgrade
                return
        current = down
    raise AssertionError("no migration drops the stale execution unique")

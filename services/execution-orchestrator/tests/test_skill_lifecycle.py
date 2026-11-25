"""Phase 3 lifecycle authority tests (doc 22 sections 5.1, 17):
T-LB1 — the transition table is the implemented table (the grid is
pinned in shared tests) AND every lifecycle write site in both
services is downstream of the shared authority in the same function
(AST guard; creation writes of a born-'draft' row are the creation
edge and exempt). T-LB2's writer half — the orchestrator transition
writer refuses an unevidenced transition and writes nothing; the
one-active race itself is backstopped by the migration's partial
unique index (uq_skill_versions_one_active) and the activation
pass's retire-before-activate order (CTL T-LB6).
"""

import ast
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.harvest.skill_library import (
    transition_version,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_TREES = [
    REPO_ROOT / "services/execution-orchestrator/src",
    REPO_ROOT / "services/control-api/src",
]
AUTHORITY_MARKERS = (
    "check_skill_transition",
    "transition_version",
    "apply_skill_transition",
    "_write_transition",
)


def _write_sites(tree: Path) -> list[tuple[str, int, str]]:
    """(file, line, function) for every lifecycle_status write whose
    enclosing function shows no authority marker."""
    violations: list[tuple[str, int, str]] = []
    for path in sorted(tree.rglob("*.py")):
        module = ast.parse(path.read_text(encoding="utf-8-sig"))
        parents: dict[int, ast.AST] = {}
        for node in ast.walk(module):
            for child in ast.iter_child_nodes(node):
                parents[id(child)] = node

        def enclosing_function(node: ast.AST) -> ast.AST | None:
            cursor = parents.get(id(node))
            while cursor is not None:
                if isinstance(
                    cursor, (ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    return cursor
                cursor = parents.get(id(cursor))
            return None

        for node in ast.walk(module):
            is_write = False
            if isinstance(node, ast.Assign):
                is_write = any(
                    isinstance(target, ast.Attribute)
                    and target.attr == "lifecycle_status"
                    for target in node.targets
                )
            elif isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg != "lifecycle_status":
                        continue
                    func = node.func
                    called = (
                        func.attr
                        if isinstance(func, ast.Attribute)
                        else getattr(func, "id", "")
                    )
                    if called == "SkillVersion" and isinstance(
                        keyword.value, ast.Constant
                    ) and keyword.value.value == "draft":
                        continue  # the creation edge: born draft
                    if called in ("update_skill_version", "SkillVersion"):
                        is_write = True
            if not is_write:
                continue
            function = enclosing_function(node)
            function_source = (
                ast.dump(function) if function is not None else ""
            )
            if not any(
                marker in function_source for marker in AUTHORITY_MARKERS
            ):
                violations.append(
                    (
                        str(path.relative_to(REPO_ROOT)),
                        node.lineno,
                        getattr(function, "name", "<module>"),
                    )
                )
    return violations


def test_t_lb1_every_lifecycle_write_is_downstream_of_the_authority():
    violations: list[tuple[str, int, str]] = []
    for tree in SOURCE_TREES:
        violations.extend(_write_sites(tree))
    assert violations == []


class _FakeRepository:
    """The transition writer's repository surface, in memory."""

    def __init__(self, version):
        self.version = version
        self.applied: list[dict] = []

    async def get_skill_version(self, version_id):
        return self.version if version_id == self.version.id else None

    async def apply_skill_transition(self, version_id, *, fields, event):
        for key, value in fields.items():
            setattr(self.version, key, value)
        self.applied.append({"fields": fields, "event": event})
        return self.version


def _version(lifecycle="draft"):
    return SimpleNamespace(
        id=uuid4(),
        skill_id=uuid4(),
        workspace_id=uuid4(),
        lifecycle_status=lifecycle,
        retired_reason=None,
        retired_at=None,
    )


@pytest.mark.asyncio
async def test_t_lb2_writer_refuses_an_unevidenced_transition():
    version = _version("draft")
    repo = _FakeRepository(version)
    with pytest.raises(ValueError, match="skill_transition_refused"):
        await transition_version(
            repo,
            version.id,
            to_status="active",
            kind="activation",
            evidence={"currency_pass": {"app_map_id": "x"}},
        )
    assert version.lifecycle_status == "draft"
    assert repo.applied == []


@pytest.mark.asyncio
async def test_t_lb2_writer_applies_an_evidenced_transition_with_its_event():
    version = _version("draft")
    repo = _FakeRepository(version)
    await transition_version(
        repo,
        version.id,
        to_status="replay_verified",
        kind="verification_replay",
        evidence={"two_clean_replays": ["r-1", "r-2"]},
        result="passed",
    )
    assert version.lifecycle_status == "replay_verified"
    assert len(repo.applied) == 1
    event = repo.applied[0]["event"]
    assert event["kind"] == "verification_replay"
    assert event["from_status"] == "draft"
    assert event["to_status"] == "replay_verified"


@pytest.mark.asyncio
async def test_writer_retirement_stamps_reason_and_time():
    version = _version("active")
    repo = _FakeRepository(version)
    await transition_version(
        repo,
        version.id,
        to_status="retired",
        kind="retirement",
        evidence={"retirement": {"retired_reason": "owner"}},
    )
    assert version.lifecycle_status == "retired"
    assert version.retired_reason == "owner"
    assert version.retired_at is not None

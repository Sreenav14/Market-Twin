"""Phase 2 login skill tests (doc 21 section 13; T-LG1..T-LG8)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent))

import pytest
from markettwin_database.models.knowledge import (
    MapElement,
    MapField,
    MapForm,
    MapPage,
    SkillReplay,
    SkillVersion,
)

from markettwin_execution_orchestrator.expectations import login_skill
from markettwin_execution_orchestrator.expectations.login_skill import (
    LOGIN_PASSWORD_KEY,
    LOGIN_USERNAME_KEY,
)

pytestmark = pytest.mark.asyncio

WS = uuid4()
APP = uuid4()
TGT = uuid4()
MAP = uuid4()


def graph_rows():
    page = MapPage(
        id=uuid4(), workspace_id=WS, application_id=APP, target_id=TGT,
        app_map_id=MAP, canonical_url="https://shop.example/login",
        route_pattern="/login", title="Sign in",
    )
    form = MapForm(
        id=uuid4(), workspace_id=WS, application_id=APP, target_id=TGT,
        app_map_id=MAP, map_page_id=page.id, map_page_state_id=uuid4(),
        form_key="login", source="harvest",
    )
    username = MapField(
        id=uuid4(), workspace_id=WS, application_id=APP, target_id=TGT,
        app_map_id=MAP, form_id=form.id, label="Email", field_type="email",
        validation_source="dom", source="harvest",
    )
    password = MapField(
        id=uuid4(), workspace_id=WS, application_id=APP, target_id=TGT,
        app_map_id=MAP, form_id=form.id, label="Password",
        field_type="password", validation_source="dom", source="harvest",
    )
    submit = MapElement(
        id=uuid4(), workspace_id=WS, application_id=APP, target_id=TGT,
        app_map_id=MAP, map_page_id=page.id, map_page_state_id=uuid4(),
        role="button", name="Sign in",
        actionability="click", safety_class="reversible",
    )
    form.submit_element_id = submit.id
    return page, form, username, password, submit


class CompileSession:
    def __init__(self, pages, forms, fields, elements):
        self._queue = [pages, forms, fields, elements]
        self.added: list[object] = []

    async def scalars(self, _stmt):
        return iter(self._queue.pop(0))

    async def scalar(self, _stmt):
        return None

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


def fake_app_map() -> SimpleNamespace:
    return SimpleNamespace(
        id=MAP, workspace_id=WS, application_id=APP, target_id=TGT
    )


async def test_lg1_compile_from_graph_stores_keys_only() -> None:
    page, form, username, password, submit = graph_rows()
    session = CompileSession([page], [form], [username, password], [submit])
    version = await login_skill.compile_login_skill(
        session,  # type: ignore[arg-type]
        app_map=fake_app_map(),  # type: ignore[arg-type]
        landing_url="https://shop.example/account",
        landing_signature="sig-123",
    )
    assert version is not None
    assert version.lifecycle_status == "draft"
    assert version.verified_fingerprint == "sig-123"
    definition = version.definition_json
    assert definition["provenance"] == "handoff-proven"
    keys = [
        step.get("test_value_key") for step in definition["steps"]
    ]
    assert keys == [None, LOGIN_USERNAME_KEY, LOGIN_PASSWORD_KEY, None]
    assert definition["success_assertion"] == {
        "url": "https://shop.example/account",
        "state_id": "sig-123",
    }


async def test_lg2_no_password_field_no_skill() -> None:
    page, form, username, _password, submit = graph_rows()
    session = CompileSession([page], [form], [username], [submit])
    version = await login_skill.compile_login_skill(
        session,  # type: ignore[arg-type]
        app_map=fake_app_map(),  # type: ignore[arg-type]
        landing_url="https://shop.example/account",
        landing_signature="sig",
    )
    assert version is None


def test_lg3_mode_filter_and_persona_carve_out() -> None:
    keys = {LOGIN_USERNAME_KEY, LOGIN_PASSWORD_KEY}
    assert login_skill.login_mode_allowed(
        run_mode="standard", is_persona_run=False, approved_keys=keys
    ) == (True, None)
    assert login_skill.login_mode_allowed(
        run_mode="read_only", is_persona_run=False, approved_keys=keys
    ) == (False, None)
    # F5(B): persona runs may replay as setup via the approved channel.
    assert login_skill.login_mode_allowed(
        run_mode="read_only", is_persona_run=True, approved_keys=keys
    ) == (True, None)
    assert login_skill.login_mode_allowed(
        run_mode="standard",
        is_persona_run=False,
        approved_keys={LOGIN_USERNAME_KEY},
    ) == (False, LOGIN_PASSWORD_KEY)


async def test_lg4_replay_resolves_values_and_verifies(monkeypatch) -> None:
    page, form, username, password, submit = graph_rows()
    definition = login_skill.build_login_definition(
        (page, form, username, password, submit),
        landing_url="https://shop.example/account",
        landing_signature="sig",
    )
    calls: list = []

    async def fake_perform(controller, handle, action, scope):
        calls.append((action, scope))
        return SimpleNamespace()

    monkeypatch.setattr(
        "markettwin_execution_orchestrator.workflow.case_execution"
        ".perform_case_action",
        fake_perform,
    )

    class Controller:
        async def verify_authenticated_role(self, *, handle, policy):
            return object()

    handle = SimpleNamespace(
        session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4()
    )
    ok, step, site = await login_skill.replay_login_definition(
        Controller(),
        handle,
        definition=definition,
        values={LOGIN_USERNAME_KEY: "user@example.com",
                LOGIN_PASSWORD_KEY: "hunter2-secret"},
        allowed_origins=("https://shop.example",),
        policy=object(),
    )
    assert (ok, step, site) == (True, None, None)
    assert [action.action for action, _ in calls] == [
        "navigate", "fill", "fill", "click",
    ]
    scope = calls[0][1]
    assert {entry.key: entry.value for entry in scope.safe_test_data} == {
        LOGIN_USERNAME_KEY: "user@example.com",
        LOGIN_PASSWORD_KEY: "hunter2-secret",
    }


class ReplaySession:
    def __init__(self):
        self.replays: list[SkillReplay] = []
        self.added: list[object] = []

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, SkillReplay):
            self.replays.append(obj)

    async def flush(self):
        return None

    async def scalars(self, _stmt):
        # The seam reads replay ROWS back (newest first) and reads
        # .result/.id off them (doc 22 section 4.4 seam).
        return iter(list(reversed(self.replays)))


def bare_version() -> SkillVersion:
    return SkillVersion(
        id=uuid4(), workspace_id=WS, skill_id=uuid4(), version_number=1,
        status="draft", lifecycle_status="draft", definition_json={},
    )


async def test_lg5_two_clean_replays_verify_two_failures_suspect() -> None:
    session = ReplaySession()
    version = bare_version()
    await login_skill.record_login_replay(
        session, version=version, app_map_id=MAP, result="passed"  # type: ignore[arg-type]
    )
    assert version.lifecycle_status == "draft"
    await login_skill.record_login_replay(
        session, version=version, app_map_id=MAP, result="passed"  # type: ignore[arg-type]
    )
    assert version.lifecycle_status == "replay_verified"

    session2 = ReplaySession()
    version2 = bare_version()
    for _ in range(2):
        await login_skill.record_login_replay(
            session2, version=version2, app_map_id=MAP, result="failed"  # type: ignore[arg-type]
        )
    assert version2.lifecycle_status == "suspect"
    replays = [o for o in session2.added if isinstance(o, SkillReplay)]
    assert all(r.context_kind == "clean" and r.model_calls == 0 for r in replays)


async def test_failed_replay_cannot_verify_using_historical_passes() -> None:
    session = ReplaySession()
    version = bare_version()
    for result in ("passed", "passed"):
        await login_skill.record_login_replay(
            session, version=version, app_map_id=MAP, result=result)
    version.lifecycle_status = "suspect"
    await login_skill.record_login_replay(
        session, version=version, app_map_id=MAP, result="failed")
    assert version.lifecycle_status == "suspect"
    assert version.last_replay_result == "failed"


def test_lg6_handoff_branch_verbatim_and_seam_ordering() -> None:
    import markettwin_execution_orchestrator.workflow.case_execution as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    attempt = source.index("_attempt_login_skill(")
    handoff = source.index("create_login_request(")
    assert attempt < handoff
    # The handoff branch's own sequence is untouched.
    for marker in (
        "wait_for_human_action_resume",
        "finish_verification(",
        'verified=True,\n            safe_to_capture=True,',
    ):
        assert marker in source


async def test_lg7_unresolvable_key_refuses_with_named_event() -> None:
    import markettwin_execution_orchestrator.workflow.case_execution as ce

    version = bare_version()
    run = SimpleNamespace(
        configuration_snapshot={
            "app_map": {"map_id": str(MAP)},
            "harness_run_mode": "standard",
        },
        run_kind="explore_test",
    )

    class Session:
        def __init__(self):
            self.added: list[object] = []

        async def get(self, _model, _pk):
            return run

        async def scalar(self, _stmt):
            return version

        async def scalars(self, _stmt):
            # select_login_version reads the candidate rows back
            # (doc 22 section 6.3 serving preference).
            return iter([version])

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            return None

        async def commit(self):
            return None

        async def rollback(self):
            return None

    session = Session()
    request = SimpleNamespace(
        test_run_id=uuid4(), journey_id=uuid4(), execution_id=uuid4(),
        allowed_origins=(),
    )
    result = await ce._attempt_login_skill(
        request=request,  # type: ignore[arg-type]
        controller=SimpleNamespace(),
        handle=SimpleNamespace(),
        policy=None,
        auth_scope=None,
        session=session,  # type: ignore[arg-type]
    )
    assert result is False
    events = [
        obj for obj in session.added
        if getattr(obj, "event_type", None) == "login_skill_refused"
    ]
    assert len(events) == 1
    assert events[0].payload == {
        "reason": "NOT_EXERCISED_UNAPPROVED_DATA",
        "key": LOGIN_USERNAME_KEY,
    }


async def test_lg8_canary_no_credential_values_in_skill_data() -> None:
    page, form, username, password, submit = graph_rows()
    session = CompileSession([page], [form], [username, password], [submit])
    version = await login_skill.compile_login_skill(
        session,  # type: ignore[arg-type]
        app_map=fake_app_map(),  # type: ignore[arg-type]
        landing_url="https://shop.example/account",
        landing_signature="sig",
    )
    assert version is not None
    blob = json.dumps(
        {
            "definition": version.definition_json,
            "package": version.package,
            "metadata": version.generation_metadata,
            "fingerprint": version.verified_fingerprint,
        }
    )
    assert "hunter2-secret" not in blob
    assert "user@example.com" not in blob
    assert LOGIN_USERNAME_KEY in blob and LOGIN_PASSWORD_KEY in blob

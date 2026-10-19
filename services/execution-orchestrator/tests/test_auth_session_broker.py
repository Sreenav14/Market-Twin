"""Bounded in-memory auth reuse never crosses run, target, account, or role."""

from datetime import timedelta
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser.auth_session_broker import (
    AuthSessionBroker,
    AuthSessionReuseRejected,
    AuthSessionScope,
    HumanSessionScope,
)
from markettwin_execution_orchestrator.browser.auth_verifier import VerifiedPrincipal


class SourceContext:
    async def storage_state(self) -> dict[str, object]:
        return {
            "cookies": [
                {"name": "synthetic", "value": "secret-test-token", "domain": "fixture.test"},
                {"name": "other", "value": "must-not-cross-origins", "domain": "other.test"},
            ],
            "origins": [{
                "origin": "http://fixture.test",
                "localStorage": [{"name": "fixture", "value": "auth-state"}],
            }],
        }


class Page:
    async def evaluate(self, _expression: str) -> object:
        return {"fixture-session": "mfa-complete"}


class InstallContext:
    cookies: list[dict[str, object]] | None = None
    script = ""

    async def add_cookies(self, cookies: list[dict[str, object]]) -> None:
        self.cookies = cookies

    async def add_init_script(self, *, script: str) -> None:
        self.script = script


@pytest.mark.asyncio
async def test_human_session_never_becomes_a_verified_identity_or_crosses_run() -> None:
    broker = AuthSessionBroker()
    scope = HumanSessionScope(uuid4(), uuid4(), "http://fixture.test")
    await broker.capture_human_session(scope=scope, context=SourceContext(), page=Page())
    grant = broker.take_human_session(run_id=scope.run_id, target_id=scope.target_id, case_id="a")
    assert isinstance(grant.scope, HumanSessionScope)
    assert not hasattr(grant.scope, "role")
    assert "secret-test-token" not in repr(grant)
    for run_id, target_id in ((uuid4(), scope.target_id), (scope.run_id, uuid4())):
        with pytest.raises(AuthSessionReuseRejected):
            broker.take_human_session(run_id=run_id, target_id=target_id, case_id="b")
    with pytest.raises(AuthSessionReuseRejected):
        broker.take(
            scope=AuthSessionScope(scope.run_id, scope.target_id, "admin", "x", scope.origin),
            case_id="b",
        )
    target = InstallContext()
    await broker.install_snapshot(snapshot=grant, context=target)
    assert target.cookies and all(cookie["domain"] == "fixture.test" for cookie in target.cookies)
    broker.revoke_human_sessions(run_id=scope.run_id, target_id=scope.target_id)
    with pytest.raises(AuthSessionReuseRejected):
        broker.take_human_session(run_id=scope.run_id, target_id=scope.target_id, case_id="b")


@pytest.mark.asyncio
async def test_verified_state_is_volatile_scoped_and_single_use_per_case() -> None:
    broker = AuthSessionBroker(ttl=timedelta(minutes=2), max_cases=2)
    scope = AuthSessionScope(
        run_id=uuid4(), target_id=uuid4(), role="user",
        account_reference="fixture-user", origin="http://fixture.test",
    )
    principal = VerifiedPrincipal("user", "fixture-user", "http://fixture.test")
    await broker.capture(
        scope=scope, principal=principal, context=SourceContext(), page=Page(),
    )
    target = InstallContext()
    await broker.install(scope=scope, case_id="case-1", context=target)
    assert target.cookies == [
        {"name": "synthetic", "value": "secret-test-token", "domain": "fixture.test"}
    ]
    assert "secret-test-token" not in repr(broker)
    assert "fixture-session" in target.script
    assert "sessionStorage.setItem" in target.script
    with pytest.raises(AuthSessionReuseRejected):
        await broker.install(scope=scope, case_id="case-1", context=InstallContext())
    other_role = AuthSessionScope(
        run_id=scope.run_id, target_id=scope.target_id, role="admin",
        account_reference="fixture-user", origin=scope.origin,
    )
    with pytest.raises(AuthSessionReuseRejected):
        await broker.install(scope=other_role, case_id="case-2", context=InstallContext())
    broker.revoke(scope)
    with pytest.raises(AuthSessionReuseRejected):
        await broker.install(scope=scope, case_id="case-2", context=InstallContext())

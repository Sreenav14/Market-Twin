"""Bounded in-memory auth reuse never crosses run, target, account, or role."""

from datetime import timedelta
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser.auth_session_broker import (
    AuthSessionBroker,
    AuthSessionReuseRejected,
    AuthSessionScope,
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

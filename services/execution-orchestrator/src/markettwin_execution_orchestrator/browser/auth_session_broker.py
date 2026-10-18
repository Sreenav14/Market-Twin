"""Short-lived in-memory authenticated state shared only by isolated cases."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast
from urllib.parse import urlsplit
from uuid import UUID

from markettwin_execution_orchestrator.browser.auth_verifier import VerifiedPrincipal


class AuthSessionReuseRejected(RuntimeError):
    """Authenticated state is absent, expired, out of scope, or already used."""


class _Context(Protocol):
    async def storage_state(self) -> dict[str, object]: ...


class _Page(Protocol):
    async def evaluate(self, expression: str) -> object: ...


class _InstallableContext(Protocol):
    async def add_cookies(self, cookies: list[dict[str, object]]) -> None: ...
    async def add_init_script(self, *, script: str) -> None: ...


@dataclass(frozen=True, slots=True)
class AuthSessionScope:
    run_id: UUID
    target_id: UUID
    role: str
    account_reference: str
    origin: str


@dataclass(frozen=True, slots=True)
class HumanSessionScope:
    """Operator-established session; identity and role are deliberately unknown."""

    run_id: UUID
    target_id: UUID
    origin: str


@dataclass(frozen=True, slots=True)
class AuthSessionSnapshot:
    scope: AuthSessionScope | HumanSessionScope
    browser_storage_state: dict[str, object] = field(repr=False)
    session_storage: dict[str, str] = field(repr=False)
    expires_at: datetime


def session_storage_init_script(snapshot: AuthSessionSnapshot) -> str:
    return (
        "(() => { if (location.origin !== " + json.dumps(snapshot.scope.origin) + ") return; "
        "const values = " + json.dumps(snapshot.session_storage) + "; "
        "for (const [key, value] of Object.entries(values)) "
        "sessionStorage.setItem(key, value); })();"
    )


class AuthSessionBroker:
    """Never serializes session values and permits at most one use per case."""

    def __init__(self, *, ttl: timedelta = timedelta(minutes=15), max_cases: int = 10) -> None:
        if ttl <= timedelta(0) or ttl > timedelta(hours=1) or not 1 <= max_cases <= 50:
            raise ValueError("Authentication reuse bounds are invalid.")
        self._ttl = ttl
        self._max_cases = max_cases
        self._snapshots: dict[AuthSessionScope | HumanSessionScope, AuthSessionSnapshot] = {}
        self._used_cases: dict[AuthSessionScope | HumanSessionScope, set[str]] = {}

    async def capture(
        self,
        *,
        scope: AuthSessionScope,
        principal: VerifiedPrincipal,
        context: _Context,
        page: _Page,
    ) -> None:
        if (
            principal.role != scope.role
            or principal.account_reference != scope.account_reference
            or principal.origin != scope.origin
        ):
            raise AuthSessionReuseRejected("Verified identity does not match reuse scope.")
        await self._capture(scope=scope, context=context, page=page)

    async def capture_human_session(
        self, *, scope: HumanSessionScope, context: _Context, page: _Page,
    ) -> None:
        """Keep separately typed state without inventing a verified principal."""
        await self._capture(scope=scope, context=context, page=page)

    async def _capture(
        self, *, scope: AuthSessionScope | HumanSessionScope, context: _Context, page: _Page,
    ) -> None:
        storage_state = await context.storage_state()
        session_storage = await page.evaluate(
            "() => Object.fromEntries(Array.from({length: sessionStorage.length}, "
            "(_, index) => { const key = sessionStorage.key(index); "
            "return [key, sessionStorage.getItem(key) ?? '']; }))"
        )
        if not isinstance(session_storage, dict):
            raise AuthSessionReuseRejected("Browser authentication state is unavailable.")
        storage_values = cast(dict[object, object], session_storage)
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            or len(key) > 512 or len(value) > 16_384
            for key, value in storage_values.items()
        ) or len(storage_values) > 100:
            raise AuthSessionReuseRejected("Browser authentication state is unavailable.")
        state_origin = storage_state
        if len(json.dumps(state_origin, separators=(",", ":"))) > 1_048_576:
            raise AuthSessionReuseRejected("Browser authentication state is too large.")
        self._snapshots[scope] = AuthSessionSnapshot(
            scope=scope,
            browser_storage_state=state_origin,
            session_storage=cast(dict[str, str], session_storage),
            expires_at=datetime.now(UTC) + self._ttl,
        )
        self._used_cases[scope] = set()

    async def install(
        self,
        *,
        scope: AuthSessionScope,
        case_id: str,
        context: _InstallableContext,
    ) -> AuthSessionSnapshot:
        snapshot = self.take(scope=scope, case_id=case_id)
        await self.install_snapshot(snapshot=snapshot, context=context)
        return snapshot

    def take_human_session(
        self, *, run_id: UUID, target_id: UUID, case_id: str,
    ) -> AuthSessionSnapshot:
        scopes = [scope for scope in self._snapshots
                  if isinstance(scope, HumanSessionScope)
                  and scope.run_id == run_id and scope.target_id == target_id]
        if not scopes:
            raise AuthSessionReuseRejected("No operator-established session is available.")
        scope = max(scopes, key=lambda item: self._snapshots[item].expires_at)
        return self.take(scope=scope, case_id=case_id)

    def take(
        self, *, scope: AuthSessionScope | HumanSessionScope, case_id: str,
    ) -> AuthSessionSnapshot:
        snapshot = self._snapshots.get(scope)
        used = self._used_cases.get(scope)
        if (
            snapshot is None or used is None or snapshot.expires_at <= datetime.now(UTC)
            or not case_id or len(case_id) > 128 or case_id in used
            or len(used) >= self._max_cases
        ):
            raise AuthSessionReuseRejected("Authenticated state cannot be reused for this case.")
        cookies = snapshot.browser_storage_state.get("cookies", [])
        if not isinstance(cookies, list):
            raise AuthSessionReuseRejected("Browser authentication state is invalid.")
        used.add(case_id)
        return snapshot

    @staticmethod
    async def install_snapshot(
        *, snapshot: AuthSessionSnapshot, context: _InstallableContext,
    ) -> None:
        scope = snapshot.scope
        cookies = snapshot.browser_storage_state.get("cookies", [])
        if not isinstance(cookies, list):
            raise AuthSessionReuseRejected("Browser authentication state is invalid.")
        origin = urlsplit(scope.origin)
        if origin.scheme not in {"http", "https"} or not origin.hostname:
            raise AuthSessionReuseRejected("Browser authentication scope is invalid.")
        scoped_cookies: list[dict[str, object]] = []
        for raw_cookie in cast(list[object], cookies):
            if not isinstance(raw_cookie, dict):
                raise AuthSessionReuseRejected("Browser authentication state is invalid.")
            cookie = cast(dict[str, object], raw_cookie)
            domain = cookie.get("domain")
            url = cookie.get("url")
            if isinstance(domain, str):
                cookie_host = domain.lstrip(".").lower()
                if origin.hostname.lower() == cookie_host or origin.hostname.lower().endswith(
                    "." + cookie_host
                ):
                    scoped_cookies.append(cookie)
            elif isinstance(url, str):
                cookie_origin = urlsplit(url)
                if (cookie_origin.scheme, cookie_origin.hostname, cookie_origin.port) == (
                    origin.scheme, origin.hostname, origin.port
                ):
                    scoped_cookies.append(cookie)
            else:
                raise AuthSessionReuseRejected("Browser authentication state is invalid.")
        await context.add_cookies(scoped_cookies)
        origins = snapshot.browser_storage_state.get("origins", [])
        if not isinstance(origins, list):
            raise AuthSessionReuseRejected("Browser authentication state is invalid.")
        storage_rows: list[dict[str, object]] = []
        for raw_item in cast(list[object], origins):
            if not isinstance(raw_item, dict):
                raise AuthSessionReuseRejected("Browser authentication state is invalid.")
            item = cast(dict[str, object], raw_item)
            if item.get("origin") == scope.origin:
                storage_rows.append(item)
        if len(storage_rows) > 1:
            raise AuthSessionReuseRejected("Browser authentication state is ambiguous.")
        local_storage: dict[str, str] = {}
        if storage_rows:
            raw_values = storage_rows[0].get("localStorage", [])
            if not isinstance(raw_values, list):
                raise AuthSessionReuseRejected("Browser authentication state is invalid.")
            for item in cast(list[object], raw_values):
                storage_item = cast(dict[str, object], item) if isinstance(item, dict) else {}
                if (
                    not isinstance(item, dict)
                    or not isinstance(storage_item.get("name"), str)
                    or not isinstance(storage_item.get("value"), str)
                ):
                    raise AuthSessionReuseRejected("Browser authentication state is invalid.")
                local_storage[cast(str, storage_item["name"])] = cast(
                    str, storage_item["value"]
                )
        # JSON encoding protects the script boundary; values are in memory only.
        session_script = session_storage_init_script(snapshot)
        script = session_script.replace(
            "const values =",
            "const localValues = " + json.dumps(local_storage) + "; "
            "for (const [key, value] of Object.entries(localValues)) "
            "localStorage.setItem(key, value); "
            "const values =",
        )
        await context.add_init_script(script=script)

    def revoke(self, scope: AuthSessionScope | HumanSessionScope) -> None:
        self._snapshots.pop(scope, None)
        self._used_cases.pop(scope, None)

    def revoke_human_sessions(self, *, run_id: UUID, target_id: UUID) -> None:
        for scope in tuple(self._snapshots):
            if (isinstance(scope, HumanSessionScope) and scope.run_id == run_id
                    and scope.target_id == target_id):
                self.revoke(scope)

    def clear(self) -> None:
        """Erase every in-memory authenticated snapshot at run teardown."""

        self._snapshots.clear()
        self._used_cases.clear()

    def purge_expired(self) -> int:
        now = datetime.now(UTC)
        expired = [
            scope for scope, snapshot in self._snapshots.items()
            if snapshot.expires_at <= now
        ]
        for scope in expired:
            self.revoke(scope)
        return len(expired)

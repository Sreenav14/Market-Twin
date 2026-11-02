"""Volatile, fixed-label network counters for the current human takeover only."""

from collections import Counter, deque
from collections.abc import Callable
from time import monotonic
from typing import Literal

NetworkDiagnosticReason = Literal[
    "target_origin_denied", "captcha_resource_denied", "unsafe_destination_ip",
    "dns_resolution_failed", "upstream_connection_failed", "browser_transport_failed",
]
NetworkDiagnosticDestination = Literal[
    "authorized_target", "known_provider", "unknown_third_party",
]
NETWORK_DIAGNOSTIC_REASONS = frozenset({
    "target_origin_denied", "captcha_resource_denied", "unsafe_destination_ip",
    "dns_resolution_failed", "upstream_connection_failed", "browser_transport_failed",
})
NETWORK_DIAGNOSTIC_DESTINATIONS = frozenset({
    "authorized_target", "known_provider", "unknown_third_party",
})


class HumanNetworkDiagnostics:
    """Keep at most 128 events for 120 seconds, without retaining destinations."""

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._events: deque[tuple[float, NetworkDiagnosticReason, NetworkDiagnosticDestination]] = (
            deque(maxlen=128)
        )

    def clear(self) -> None:
        self._events.clear()

    def record(
        self, reason: NetworkDiagnosticReason, destination: NetworkDiagnosticDestination,
    ) -> None:
        if reason not in NETWORK_DIAGNOSTIC_REASONS:
            raise ValueError("Unknown network diagnostic reason.")
        if destination not in NETWORK_DIAGNOSTIC_DESTINATIONS:
            raise ValueError("Unknown network diagnostic destination.")
        now = self._clock()
        self._prune(now)
        self._events.append((now, reason, destination))

    def snapshot(self) -> tuple[dict[str, str | int], ...]:
        self._prune(self._clock())
        counts = Counter((reason, destination) for _, reason, destination in self._events)
        return tuple(
            {"reason": reason, "destination": destination, "count": count}
            for (reason, destination), count in sorted(counts.items())
        )

    def _prune(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= 120:
            self._events.popleft()

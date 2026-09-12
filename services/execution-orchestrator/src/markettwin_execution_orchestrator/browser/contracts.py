"""Internal browser execution contracts for MarketTwin."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal
from uuid import UUID

MAX_MODEL_ARIA_SNAPSHOT_CHARS = 2_000

NetworkPolicy = Literal["public_only", "local_development"]
BrowserSessionState = Literal[
    "starting",
    "open",
    "human_control",
    "closed",
    "failed",
]

@dataclass(frozen=True, slots=True)
class BrowserSessionArtifacts:
    """Local evidence produced when one browser session closes."""
    
    trace_paths: tuple[Path, ...] = ()
    console_log_path: Path | None = None
    page_log_path: Path | None = None
    network_log_path: Path | None = None

class StoredArtifact:
    """A stored artifact from a browser session."""

    storage_provider: str
    bucket: str
    object_key: str
    content_type: str
    size_bytes: int
    
    
@dataclass(frozen=True, slots=True)
class AllowedOrigin:
    """One exact origin MarketTwin is authorized to access."""

    scheme: Literal["http", "https"]
    hostname: str
    port: int | None = None
    include_subdomains: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedAddress:
    """One DNS result validated by MarketTwin."""

    address: str
    family: Literal[4, 6]


@dataclass(frozen=True, slots=True)
class FailedRequestRecord:
    """Safe metadata for one failed browser request."""

    url: str
    method: str
    resource_type: str
    error_text: str


@dataclass(frozen=True, slots=True)
class BrowserObservation:
    """Compact browser state returned to Persona Agents after an action."""

    url: str
    title: str
    aria_snapshot: str
    console_errors_since_last_action: tuple[str, ...] = ()
    page_errors_since_last_action: tuple[str, ...] = ()
    failed_requests_since_last_action: tuple[FailedRequestRecord, ...] = ()
    accessibility_snapshot_path: str | None = None
    page_count: int = 1
    action_number: int = 0
    screenshot_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return an ADK/tool-safe dictionary."""
        result = asdict(self)
        if len(self.aria_snapshot) > MAX_MODEL_ARIA_SNAPSHOT_CHARS:
            result["aria_snapshot"] = (
                self.aria_snapshot[:MAX_MODEL_ARIA_SNAPSHOT_CHARS]
                + "\n# Snapshot truncated for model context; full snapshot is stored as evidence."
            )
        return result


@dataclass(frozen=True, slots=True)
class BrowserActionResult:
    """Result of one deterministic MarketTwin browser action."""

    action: str
    observation: BrowserObservation

    def to_dict(self) -> dict[str, object]:
        """Return an ADK/tool-safe dictionary."""

        return {
            "action": self.action,
            "observation": self.observation.to_dict(),
        }


def _string_list() -> list[str]:
    return []


def _failed_request_list() -> list[FailedRequestRecord]:
    return []


@dataclass(slots=True)
class BrowserEventBuffer:
    """Per-session event buffers with incremental and cumulative views."""

    console_errors: list[str] = field(default_factory=_string_list)
    page_errors: list[str] = field(default_factory=_string_list)
    failed_requests: list[FailedRequestRecord] = field(
        default_factory=_failed_request_list
    )
    all_console_errors: list[str] = field(default_factory=_string_list)
    all_page_errors: list[str] = field(default_factory=_string_list)
    all_failed_requests: list[FailedRequestRecord] = field(
        default_factory=_failed_request_list
    )

    def record_console_error(self, message: str) -> None:
        self.console_errors.append(message)
        self.all_console_errors.append(message)

    def record_page_error(self, message: str) -> None:
        self.page_errors.append(message)
        self.all_page_errors.append(message)

    def record_failed_request(self, request: FailedRequestRecord) -> None:
        self.failed_requests.append(request)
        self.all_failed_requests.append(request)


@dataclass(frozen=True, slots=True)
class BrowserSessionHandle:
    """Opaque handle safe for orchestration code to retain."""

    session_id: UUID
    execution_id: UUID
    journey_id: UUID

""" Domain state for bounded MarketTwin mission execution. """

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID


class RunStatus(StrEnum):
    """ Lifecycle status for a MarketTwin execution run"""
    
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    POLICY_BLOCKED = "policy_blocked"
    
    
@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """ Hard limits enforced by MarketTwin, not by LLM."""
    
    max_steps: int = 10
    max_duration_seconds: int = 180
    max_retries_per_action: int = 1
    
@dataclass(frozen=True, slots=True)
class MissionExecutionRequest:
    """ Validated request passed into the execution orchestrator. """
    
    run_id: UUID
    target_url: str
    allowed_domains: tuple[str,...]
    mission: str
    authorization_confirmed: bool
    limits: ExecutionLimits = field(default_factory= ExecutionLimits)
    
@dataclass(frozen=True, slots=True)
class MissionExecutionResult:
    """ Structured result returned by mission execution. """
    
    run_id: UUID
    status: RunStatus
    final_url: str | None = None
    summary: str | None = None
    tool_calls: tuple[str,...] = ()
    errors: tuple[str,...] = ()
    
    
    
    
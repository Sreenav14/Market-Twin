"""Google ADK model-call observability without taking over its agent loop."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from markettwin_shared.observability import model_token_usage_from_adk
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.models.model_factory import (
    ModelRuntimeConfig,
)
from markettwin_execution_orchestrator.persistence.observability_repository import (
    ObservabilityRepository,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class _PendingInvocation:
    invocation_id: UUID
    started_at: datetime
    started_monotonic: float


class AdkModelInvocationObserver:
    """Observe each ADK model turn via callbacks and persist its usage."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        test_run_id: UUID,
        agent_snapshot_id: UUID,
        agent_role: str,
        runtime_agent_name: str,
        model_config: ModelRuntimeConfig,
        journey_id: UUID | None = None,
        execution_id: UUID | None = None,
    ) -> None:
        self._session = session
        self._repository = ObservabilityRepository(session)
        self._test_run_id = test_run_id
        self._journey_id = journey_id
        self._execution_id = execution_id
        self._agent_snapshot_id = agent_snapshot_id
        self._agent_role = agent_role
        self._runtime_agent_name = runtime_agent_name
        self._model_config = model_config
        self._sequence = 0
        self._pending: dict[str, list[_PendingInvocation]] = {}

    async def before_model_callback(
        self,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
    ) -> None:
        """Record the start of one ADK-owned model turn."""

        del llm_request

        self._sequence += 1
        invocation_id = uuid4()
        started_at = _utc_now()

        await self._repository.start_model_invocation(
            invocation_id=invocation_id,
            test_run_id=self._test_run_id,
            journey_id=self._journey_id,
            execution_id=self._execution_id,
            agent_snapshot_id=self._agent_snapshot_id,
            agent_role=self._agent_role,
            runtime_agent_name=self._runtime_agent_name,
            runtime_invocation_id=callback_context.invocation_id,
            invocation_sequence=self._sequence,
            attempt_number=1,
            model_provider=self._model_config.provider,
            model_name=self._model_config.model_name,
            started_at=started_at,
            metadata={
                "retry_visibility": "provider_internal_retries_not_individually_observable",
            },
        )
        await self._session.commit()

        self._pending.setdefault(
            callback_context.invocation_id,
            [],
        ).append(
            _PendingInvocation(
                invocation_id=invocation_id,
                started_at=started_at,
                started_monotonic=perf_counter(),
            )
        )

        return None

    async def after_model_callback(
        self,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> None:
        """Record provider-reported usage for one completed ADK model turn."""

        pending = self._pop_pending(
            callback_context.invocation_id
        )
        completed_at = _utc_now()
        latency_ms = max(
            0,
            round(
                (perf_counter() - pending.started_monotonic)
                * 1000
            ),
        )

        status = (
            "failed"
            if llm_response.error_code
            else "completed"
        )

        metadata: dict[str, object] = {}
        if llm_response.interaction_id:
            metadata["interaction_id"] = llm_response.interaction_id

        await self._repository.finish_model_invocation(
            invocation_id=pending.invocation_id,
            status=status,
            completed_at=completed_at,
            latency_ms=latency_ms,
            usage=model_token_usage_from_adk(
                llm_response.usage_metadata
            ),
            model_version=llm_response.model_version,
            error_code=(
                str(llm_response.error_code)
                if llm_response.error_code
                else None
            ),
            error_summary=llm_response.error_message,
            metadata=metadata,
        )
        await self._session.commit()

        return None

    async def on_model_error_callback(
        self,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
        error: Exception,
    ) -> None:
        """Record a failed ADK model turn and let ADK preserve normal behavior."""

        del llm_request

        pending = self._pop_pending(
            callback_context.invocation_id
        )
        completed_at = _utc_now()
        latency_ms = max(
            0,
            round(
                (perf_counter() - pending.started_monotonic)
                * 1000
            ),
        )

        error_name = type(error).__name__
        error_text = _safe_error_summary(error)
        rate_limited = (
            "ratelimit" in error_name.casefold()
            or "rate limit" in error_text.casefold()
        )

        await self._repository.finish_model_invocation(
            invocation_id=pending.invocation_id,
            status=(
                "rate_limited"
                if rate_limited
                else "failed"
            ),
            completed_at=completed_at,
            latency_ms=latency_ms,
            error_code=error_name[:100],
            error_summary=error_text,
        )
        await self._session.commit()

        return None

    def _pop_pending(
        self,
        runtime_invocation_id: str,
    ) -> _PendingInvocation:
        calls = self._pending.get(
            runtime_invocation_id
        )

        if not calls:
            raise RuntimeError(
                "ADK model callback completed without a matching start."
            )

        pending = calls.pop(0)

        if not calls:
            self._pending.pop(
                runtime_invocation_id,
                None,
            )

        return pending



def _safe_error_summary(
    error: Exception,
) -> str:
    """Return a bounded provider error summary with configured API keys redacted."""

    value = str(error)

    for variable in (
        "MODEL_API_KEY",
        "OPENAI_API_KEY",
    ):
        secret = os.getenv(variable)
        if secret:
            value = value.replace(
                secret,
                "[REDACTED]",
            )

    return value[:4000]

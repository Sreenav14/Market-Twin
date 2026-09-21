"""Visual-verifier snapshot and model-attempt telemetry."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

from markettwin_shared.observability import (
    AgentRuntimeSnapshotSpec,
    model_token_usage_from_litellm,
)

from markettwin_evaluation_worker.persistence.observability_repository import (
    EvaluationObservabilityRepository,
)

VISUAL_SNAPSHOT_SCHEMA_VERSION = 1
VISUAL_AGENT_VERSION = "1"
VISUAL_TEMPLATE_VERSION = "python-v1"


@dataclass(frozen=True, slots=True)
class VisualModelConfig:
    """Safe configuration for the targeted visual verifier."""

    model_name: str
    max_tokens: int
    temperature: int
    max_attempts: int

    @property
    def provider(self) -> str | None:
        if "/" not in self.model_name:
            return None
        return self.model_name.split("/", 1)[0]

    def snapshot(self) -> dict[str, object]:
        return {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "max_attempts": self.max_attempts,
        }


class VisualInvocationRecorder:
    """Persist every explicit retry attempt made by the visual verifier."""

    def __init__(
        self,
        *,
        repository: EvaluationObservabilityRepository,
        test_run_id: UUID,
        agent_snapshot_id: UUID,
        config: VisualModelConfig,
    ) -> None:
        self._repository = repository
        self._test_run_id = test_run_id
        self._agent_snapshot_id = agent_snapshot_id
        self._config = config
        self._pending: dict[UUID, float] = {}

    async def start(
        self,
        *,
        attempt_number: int,
        criterion: str,
    ) -> UUID:
        invocation_id = uuid4()
        self._pending[invocation_id] = perf_counter()

        await self._repository.start_invocation(
            invocation_id=invocation_id,
            test_run_id=self._test_run_id,
            agent_snapshot_id=self._agent_snapshot_id,
            attempt_number=attempt_number,
            model_provider=self._config.provider,
            model_name=self._config.model_name,
            started_at=datetime.now(UTC),
            metadata={
                "criterion": criterion,
            },
        )

        return invocation_id

    async def completed(
        self,
        *,
        invocation_id: UUID,
        response: object,
    ) -> None:
        await self._repository.finish_invocation(
            invocation_id=invocation_id,
            status="completed",
            completed_at=datetime.now(UTC),
            latency_ms=self._latency_ms(invocation_id),
            usage=model_token_usage_from_litellm(
                response
            ),
        )

    async def failed(
        self,
        *,
        invocation_id: UUID,
        error: Exception,
        rate_limited: bool,
    ) -> None:
        await self._repository.finish_invocation(
            invocation_id=invocation_id,
            status=(
                "rate_limited"
                if rate_limited
                else "failed"
            ),
            completed_at=datetime.now(UTC),
            latency_ms=self._latency_ms(invocation_id),
            error_code=type(error).__name__[:100],
            error_summary=_safe_error_summary(error),
        )

    def _latency_ms(
        self,
        invocation_id: UUID,
    ) -> int:
        started = self._pending.pop(
            invocation_id
        )
        return max(
            0,
            round(
                (perf_counter() - started)
                * 1000
            ),
        )


def build_visual_runtime_snapshot(
    *,
    test_run_id: UUID,
    config: VisualModelConfig,
    effective_instruction: str,
) -> AgentRuntimeSnapshotSpec:
    """Build the stable visual-verifier configuration for one evaluation."""

    return AgentRuntimeSnapshotSpec(
        test_run_id=str(test_run_id),
        agent_role="visual_verifier",
        runtime_agent_name="markettwin_visual_verifier",
        runtime_kind="litellm_direct",
        agent_version=VISUAL_AGENT_VERSION,
        snapshot_schema_version=VISUAL_SNAPSHOT_SCHEMA_VERSION,
        template_id="visual_verifier",
        template_version=VISUAL_TEMPLATE_VERSION,
        model_provider=config.provider,
        model_name=config.model_name,
        model_configuration=config.snapshot(),
        base_instruction=effective_instruction,
        effective_instruction=effective_instruction,
        runtime_prompt=None,
        tools=(),
        metadata={
            "invocation_scope": "one criterion per call",
        },
    )



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

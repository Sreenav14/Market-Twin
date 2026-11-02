"""Durable per-run model reservations and usage, independent of report transactions."""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from os import getenv
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from markettwin_database.models.execution import RunEvent
from markettwin_database.models.testing import TestRun


class ModelBudgetExceeded(ValueError):
    """No additional provider request may be made for this run."""


@dataclass(frozen=True)
class _Budget:
    session: AsyncSession
    run_id: UUID
    max_calls: int
    max_tokens: int

    @property
    def engine(self) -> AsyncEngine:
        bind = self.session.bind
        return bind.engine if isinstance(bind, AsyncConnection) else bind


_budget: ContextVar[_Budget | None] = ContextVar("markettwin_model_budget", default=None)
_role: ContextVar[str] = ContextVar("markettwin_model_role", default="execution")


@contextmanager
def model_budget(session: AsyncSession, run_id: UUID) -> Generator[None]:
    """Share limits across execution/evaluation and retain usage through retries."""
    max_calls = int(getenv("MARKETTWIN_RUN_MAX_MODEL_CALLS", "512"))
    max_tokens = int(getenv("MARKETTWIN_RUN_MAX_MODEL_TOKENS", "2000000"))
    if max_calls <= 0 or max_tokens <= 0:
        raise ValueError("Run model budgets must be positive.")
    token = _budget.set(_Budget(session, run_id, max_calls, max_tokens))
    try:
        yield
    finally:
        _budget.reset(token)


@contextmanager
def model_role(role: str) -> Generator[None]:
    token = _role.set(role)
    try:
        yield
    finally:
        _role.reset(token)


@dataclass
class ModelCall:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def record(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is not None:
            prompt = getattr(usage, "prompt_tokens", None)
            completion = getattr(usage, "completion_tokens", None)
            if type(prompt) is int and type(completion) is int and min(prompt, completion) >= 0:
                self.prompt_tokens, self.completion_tokens = prompt, completion


@asynccontextmanager
async def model_call(
    *, model: str, input_tokens: int, output_tokens: int,
) -> AsyncGenerator[ModelCall]:
    """Reserve before sending; failed/unknown calls retain their full reservation.

    Input counts come from the provider adapter's tokenizer. This bounds calls and
    estimated token exposure, not currency: provider prices and image tokenization
    may differ. Actual reported usage replaces a reservation for subsequent calls.
    """
    budget = _budget.get()
    call = ModelCall()
    if budget is None:
        yield call
        return
    if input_tokens < 0 or output_tokens <= 0:
        raise ValueError("Model token reservations must be nonnegative with positive output.")
    call_id = str(uuid4())
    async with AsyncSession(budget.engine, expire_on_commit=False) as session, session.begin():
        # Separate namespace avoids locks held by execution/report transactions.
        await session.execute(text(
            "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"
        ), {"key": f"markettwin-model-budget:{budget.run_id}"})
        run_id = await session.scalar(select(TestRun.id).where(
            TestRun.id == budget.run_id,
        ))
        if run_id is None:
            raise ModelBudgetExceeded("The model run no longer exists.")
        events = (await session.scalars(select(RunEvent).where(
            RunEvent.test_run_id == budget.run_id,
            RunEvent.event_type.in_((
                "model.budget.configured", "model.call.reserved", "model.call.completed",
            )),
        ))).all()
        limits = next((event.payload for event in events
                       if event.event_type == "model.budget.configured"), None)
        if limits is None:
            limits = {"max_calls": budget.max_calls, "max_tokens": budget.max_tokens}
            session.add(RunEvent(
                test_run_id=budget.run_id, event_type="model.budget.configured", payload=limits,
            ))
        reserved: dict[str, int] = {}
        actual: dict[str, int] = {}
        for event in events:
            payload = event.payload
            if event.event_type == "model.budget.configured":
                continue
            identifier = str(payload["call_id"])
            if event.event_type == "model.call.reserved":
                reserved[identifier] = int(str(payload["reserved_tokens"]))
            elif payload.get("total_tokens") is not None:
                actual[identifier] = int(str(payload["total_tokens"]))
        charged = sum(actual.get(identifier, value) for identifier, value in reserved.items())
        if len(reserved) >= int(str(limits["max_calls"])) or (
            charged + input_tokens + output_tokens > int(str(limits["max_tokens"]))
        ):
            raise ModelBudgetExceeded("The run's model call/token budget is exhausted.")
        session.add(RunEvent(
            test_run_id=budget.run_id, event_type="model.call.reserved",
            payload={"call_id": call_id, "model": model, "role": _role.get(),
                     "reserved_tokens": input_tokens + output_tokens,
                     "estimated_input_tokens": input_tokens, "max_output_tokens": output_tokens},
        ))
    try:
        yield call
    finally:
        if call.prompt_tokens is not None and call.completion_tokens is not None:
            async with AsyncSession(budget.engine) as session, session.begin():
                session.add(RunEvent(
                    test_run_id=budget.run_id, event_type="model.call.completed",
                    payload={"call_id": call_id, "model": model, "role": _role.get(),
                             "prompt_tokens": call.prompt_tokens,
                             "completion_tokens": call.completion_tokens,
                             "total_tokens": call.prompt_tokens + call.completion_tokens},
                ))

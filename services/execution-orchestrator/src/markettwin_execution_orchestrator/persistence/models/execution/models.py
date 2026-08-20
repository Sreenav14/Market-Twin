"""SQLAlchemy models for MarketTwin journey execution."""

from datetime import datetime
from uuid import UUID, uuid4

from markettwin_database import Base
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class AgentExecution(Base):
    __tablename__ = "agent_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('pending', 'queued', 'running', 'completed', 'failed', "
            "'timed_out', 'cancelled', 'policy_blocked')",
            name="ck_agent_executions_status_allowed",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('passed', 'failed', 'partial', 'inconclusive')",
            name="ck_agent_executions_outcome_allowed",
        ),
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_agent_executions_attempt_positive",
        ),
        UniqueConstraint(
            "journey_id",
            "attempt_number",
            name="uq_agent_executions_journey_attempt",
        ),
        UniqueConstraint(
            "id",
            "journey_id",
            name="uq_agent_executions_id_journey",
        ),
        {"schema": "execution"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    journey_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.persona_journeys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )

    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)

    runtime_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="google_adk",
        server_default=text("'google_adk'"),
    )

    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BrowserSession(Base):
    __tablename__ = "browser_sessions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('starting', 'open', 'closed', 'failed')",
            name="ck_browser_sessions_state_allowed",
        ),
        UniqueConstraint(
            "execution_id",
            name="uq_browser_sessions_execution_id",
        ),
        UniqueConstraint(
            "execution_id",
            "id",
            name="uq_browser_sessions_execution_id_id",
        ),
        {"schema": "execution"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution.agent_executions.id", ondelete="CASCADE"),
        nullable=False,
    )

    browser_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="chromium",
        server_default=text("'chromium'"),
    )

    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="starting",
        server_default=text("'starting'"),
    )

    context_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExecutionStep(Base):
    __tablename__ = "execution_steps"
    __table_args__ = (
        CheckConstraint("step_number >= 1", name="ck_execution_steps_number_positive"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'policy_blocked')",
            name="ck_execution_steps_status_allowed",
        ),
        UniqueConstraint(
            "execution_id",
            "step_number",
            name="uq_execution_steps_execution_number",
        ),
        UniqueConstraint(
            "execution_id",
            "id",
            name="uq_execution_steps_execution_id_id",
        ),
        {"schema": "execution"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution.agent_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)

    action_summary: Mapped[str] = mapped_column(Text, nullable=False)
    observation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('allowed', 'blocked', 'requires_human')",
            name="ck_policy_decisions_decision_allowed",
        ),
        ForeignKeyConstraint(
            ["execution_id", "step_id"],
            ["execution.execution_steps.execution_id", "execution.execution_steps.id"],
            ondelete="CASCADE",
        ),
        {"schema": "execution"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution.agent_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    step_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_code: Mapped[str] = mapped_column(String(100), nullable=False)
    reason_summary: Mapped[str] = mapped_column(Text, nullable=False)

    details: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = {"schema": "execution"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    test_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.test_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    journey_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.persona_journeys.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    execution_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution.agent_executions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(String(150), nullable=False)

    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class HumanActionRequest(Base):
    __tablename__ = "human_action_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type IN ('login', 'password', 'mfa', 'captcha', 'other')",
            name="ck_human_action_requests_type_allowed",
        ),
        CheckConstraint(
            "status IN ('pending', 'leased', 'completed', 'cancelled', 'expired')",
            name="ck_human_action_requests_status_allowed",
        ),
        ForeignKeyConstraint(
            ["execution_id", "browser_session_id"],
            ["execution.browser_sessions.execution_id", "execution.browser_sessions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["execution_id", "requested_by_step_id"],
            ["execution.execution_steps.execution_id", "execution.execution_steps.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "browser_session_id",
            "id",
            name="uq_human_action_requests_browser_id",
        ),
        {"schema": "execution"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    browser_session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requested_by_step_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    request_type: Mapped[str] = mapped_column(String(32), nullable=False)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )

    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HumanControlLease(Base):
    __tablename__ = "human_control_leases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["browser_session_id", "request_id"],
            [
                "execution.human_action_requests.browser_session_id",
                "execution.human_action_requests.id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "lease_token_hash",
            name="uq_human_control_leases_token_hash",
        ),
        {"schema": "execution"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    browser_session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution.browser_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    lease_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
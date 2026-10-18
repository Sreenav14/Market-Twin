"""SQLAlchemy models for MarketTwin journey execution."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
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

from markettwin_database.base import Base


class AgentExecution(Base):
    __tablename__ = "agent_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('pending', 'queued', 'running', 'completed', 'failed', "
            "'timed_out', 'cancelled', 'policy_blocked', 'skipped')",
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


class AgentRuntimeSnapshot(Base):
    """Immutable semantic configuration used for an agent execution."""

    __tablename__ = "agent_runtime_snapshots"
    __table_args__ = (
        CheckConstraint(
            "agent_role IN ('meta', 'persona', 'visual_verifier', 'evaluator')",
            name="ck_agent_runtime_snapshots_role_allowed",
        ),
        CheckConstraint(
            "agent_version >= 1",
            name="ck_agent_runtime_snapshots_agent_version_positive",
        ),
        CheckConstraint(
            "snapshot_schema_version >= 1",
            name="ck_agent_runtime_snapshots_schema_version_positive",
        ),
        CheckConstraint(
            "execution_id IS NULL OR journey_id IS NOT NULL",
            name="ck_agent_runtime_snapshots_execution_requires_journey",
        ),
        ForeignKeyConstraint(
            ["test_run_id", "journey_id"],
            [
                "testing.persona_journeys.test_run_id",
                "testing.persona_journeys.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["execution_id", "journey_id"],
            [
                "execution.agent_executions.id",
                "execution.agent_executions.journey_id",
            ],
            ondelete="CASCADE",
        ),
        {"schema": "execution"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    test_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.test_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    journey_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )

    execution_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )

    agent_role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    runtime_kind: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    runtime_agent_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    agent_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    snapshot_schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    template_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    template_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    model_provider: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    model_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    model_configuration: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    base_instruction: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    effective_instruction: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    runtime_prompt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    persona_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    mission_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    success_criteria: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    tools: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    policy_references: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    metadata_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    observability_backend: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    trace_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    snapshot_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class BrowserSession(Base):
    __tablename__ = "browser_sessions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('starting', 'open', 'closed', 'failed')",
            name="ck_browser_sessions_state_allowed",
        ),
        CheckConstraint(
            "control_mode IN ('agent', 'human_pending', 'human', 'verifying', 'none')",
            name="ck_browser_sessions_control_mode_allowed",
        ),
        CheckConstraint(
            "control_generation >= 0",
            name="ck_browser_sessions_generation_nonnegative",
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

    control_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="agent",
        server_default=text("'agent'"),
    )
    control_generation: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
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


class AgentPromptDraft(Base):
    """A user's saved edit; the original runtime snapshot stays immutable."""

    __tablename__ = "agent_prompt_drafts"
    __table_args__ = {"schema": "execution"}

    snapshot_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution.agent_runtime_snapshots.id", ondelete="CASCADE"),
        primary_key=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    prompt_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
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


class ExecutionPauseRequest(Base):
    """Durable operator intent; only the worker acknowledges a safe pause."""

    __tablename__ = "pause_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'paused', 'resume_requested', 'resumed', 'skipped', "
            "'cancelled', 'expired', 'unavailable')", name="ck_pause_requests_status_allowed",
        ),
        CheckConstraint("generation >= 0", name="ck_pause_requests_generation_nonnegative"),
        ForeignKeyConstraint(
            ["execution_id", "browser_session_id"],
            ["execution.browser_sessions.execution_id", "execution.browser_sessions.id"],
            ondelete="CASCADE",
        ),
        Index(
            "uq_active_pause_per_browser", "browser_session_id", unique=True,
            postgresql_where=text("status IN ('requested', 'paused', 'resume_requested')"),
        ),
        {"schema": "execution"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    test_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("testing.test_runs.id", ondelete="CASCADE"),
    )
    journey_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("testing.persona_journeys.id", ondelete="CASCADE"),
    )
    execution_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    browser_session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("core.users.id", ondelete="RESTRICT"),
    )
    resume_requested_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("core.users.id", ondelete="RESTRICT"),
    )
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    human_request_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("execution.human_action_requests.id", ondelete="SET NULL"),
    )
    last_durable_step_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("execution.execution_steps.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="requested")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HumanActionRequest(Base):
    __tablename__ = "human_action_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type IN ('login', 'password', 'mfa', 'captcha', 'other')",
            name="ck_human_action_requests_type_allowed",
        ),
        CheckConstraint(
            "status IN ('pending', 'leased', 'completed', 'cancelled', 'expired', 'skipped')",
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
        Index(
            "uq_human_action_requests_execution_idempotency",
            "execution_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        {"schema": "execution"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    browser_session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requested_by_step_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)

    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    terminal_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

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
        CheckConstraint("generation >= 0", name="ck_human_control_leases_generation_nonnegative"),
        Index(
            "uq_active_human_lease_per_browser",
            "browser_session_id",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
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
    generation: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActionApprovalRequest(Base):
    """One explicit human decision bound to one immutable proposed action."""

    __tablename__ = "action_approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired', 'consumed', 'cancelled')",
            name="ck_action_approval_requests_status_allowed",
        ),
        CheckConstraint(
            "length(action_fingerprint) = 64", name="ck_action_approval_fingerprint_sha256"
        ),
        CheckConstraint(
            "length(resource_fingerprint) = 64", name="ck_action_approval_resource_sha256"
        ),
        CheckConstraint("policy_version >= 1", name="ck_action_approval_policy_positive"),
        CheckConstraint(
            "control_generation >= 0", name="ck_action_approval_generation_nonnegative"
        ),
        ForeignKeyConstraint(
            ["execution_id", "step_id"],
            ["execution.execution_steps.execution_id", "execution.execution_steps.id"],
            ondelete="CASCADE",
        ),
        Index(
            "uq_active_action_approval_per_step",
            "execution_id",
            "step_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'approved')"),
        ),
        {"schema": "execution"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    test_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.test_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution.agent_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    browser_session_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution.browser_sessions.id", ondelete="SET NULL"),
    )
    step_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    action_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    control_generation: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    action_summary: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActionApprovalReceipt(Base):
    """Durable no-replay fence written before a sensitive action is dispatched."""

    __tablename__ = "action_approval_receipts"
    __table_args__ = (
        CheckConstraint(
            "dispatch_state IN ('claimed', 'completed', 'failed_before_effect', 'uncertain')",
            name="ck_action_approval_receipts_state_allowed",
        ),
        {"schema": "execution"},
    )

    approval_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution.action_approval_requests.id", ondelete="CASCADE"),
        primary_key=True,
    )
    action_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    dispatch_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="claimed",
        server_default=text("'claimed'"),
    )
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExecutionSuspension(Base):
    """Durable, token-free continuation cursor for a paused execution."""

    __tablename__ = "execution_suspensions"
    __table_args__ = (
        CheckConstraint("checkpoint_version >= 1", name="ck_suspensions_version_positive"),
        CheckConstraint("owner_generation >= 0", name="ck_suspensions_generation_nonnegative"),
        CheckConstraint("planned_step_index >= 0", name="ck_suspensions_step_nonnegative"),
        CheckConstraint("resume_count >= 0", name="ck_suspensions_resume_nonnegative"),
        CheckConstraint(
            "active_deadline_remaining_ms >= 0",
            name="ck_suspensions_deadline_nonnegative",
        ),
        CheckConstraint(
            "status IN ('waiting', 'ready', 'consumed', 'abandoned')",
            name="ck_suspensions_status_allowed",
        ),
        CheckConstraint(
            "phase IN ('auth_preflight', 'case_action', 'assertion')",
            name="ck_suspensions_phase_allowed",
        ),
        ForeignKeyConstraint(
            ["execution_id", "browser_session_id"],
            ["execution.browser_sessions.execution_id", "execution.browser_sessions.id"],
            ondelete="CASCADE",
        ),
        Index(
            "uq_active_suspension_per_run",
            "test_run_id",
            unique=True,
            postgresql_where=text("status IN ('waiting', 'ready')"),
        ),
        UniqueConstraint("test_run_id", "checkpoint_version", name="uq_suspensions_run_version"),
        {"schema": "execution"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    test_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.test_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    journey_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.persona_journeys.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    browser_session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    pending_request_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution.human_action_requests.id", ondelete="SET NULL"),
    )
    pending_approval_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution.action_approval_requests.id", ondelete="SET NULL",
                   name="fk_suspensions_pending_approval"),
    )
    last_durable_step_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("execution.execution_steps.id", ondelete="SET NULL"),
    )
    checkpoint_version: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    planned_step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    active_deadline_remaining_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    suspended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    human_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resume_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="waiting",
        server_default=text("'waiting'"),
    )

"""SQLAlchemy models for MarketTwin evaluation results."""

from datetime import datetime
from uuid import UUID, uuid4

from markettwin_database import Base
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
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


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="ck_findings_severity_allowed",
        ),
        CheckConstraint(
            "status IN ('open', 'resolved', 'dismissed')",
            name="ck_findings_status_allowed",
        ),
        UniqueConstraint(
            "test_run_id",
            "id",
            name="uq_findings_test_run_id_id",
        ),
        {"schema": "evaluation"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    test_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.test_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="open",
        server_default=text("'open'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class FindingJourney(Base):
    __tablename__ = "finding_journeys"
    __table_args__ = {"schema": "evaluation"}

    finding_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evaluation.findings.id", ondelete="CASCADE"),
        primary_key=True,
    )

    journey_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.persona_journeys.id", ondelete="CASCADE"),
        primary_key=True,
    )


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"
    __table_args__ = (
        CheckConstraint(
            "(step_id IS NOT NULL AND artifact_id IS NULL) "
            "OR (step_id IS NULL AND artifact_id IS NOT NULL)",
            name="ck_finding_evidence_exactly_one_reference",
        ),
        UniqueConstraint(
            "finding_id",
            "step_id",
            name="uq_finding_evidence_finding_step",
        ),
        UniqueConstraint(
            "finding_id",
            "artifact_id",
            name="uq_finding_evidence_finding_artifact",
        ),
        {"schema": "evaluation"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    finding_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evaluation.findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    step_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("execution.execution_steps.id", ondelete="CASCADE"),
        nullable=True,
    )

    artifact_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence.artifacts.id", ondelete="CASCADE"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "version >= 1",
            name="ck_reports_version_positive",
        ),
        CheckConstraint(
            "status IN ('generating', 'completed', 'failed')",
            name="ck_reports_status_allowed",
        ),
        UniqueConstraint(
            "test_run_id",
            "version",
            name="uq_reports_test_run_version",
        ),
        {"schema": "evaluation"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    test_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.test_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="generating",
        server_default=text("'generating'"),
    )

    executive_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    report_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
import type {
  FindingSeverity,
  JourneyOutcome,
  TestRunStatus,
} from "../../lib/api";
import { statusLabel } from "../../lib/format";

const success = new Set([
  "active",
  "authorized",
  "completed",
  "passed",
  "healthy",
]);
const danger = new Set([
  "failed",
  "revoked",
  "expired",
  "not authorized",
  "critical",
  "high",
]);
const warning = new Set([
  "partial",
  "medium",
  "timed_out",
  "policy_blocked",
  "awaiting_human",
  "human_action_required",
  "paused",
  "blocked",
  "inconclusive",
  "unverified",
]);
const info = new Set([
  "running",
  "planning",
  "queued",
  "evaluating",
  "evaluation_pending",
  "generating",
  "low",
]);

export type BadgeTone = "success" | "danger" | "warning" | "info" | "neutral";

/**
 * The one badge primitive (Hallmark signed-in SI-17): every pill in the
 * product renders through here — same markup, same tones, two sizes.
 * `glyph` renders inside the dot span (pass "" for the plain CSS dot);
 * omit it for a word-only pill.
 */
export function StatusPill({
  tone,
  glyph,
  size,
  title,
  role,
  children,
}: {
  tone: BadgeTone;
  glyph?: string;
  size?: "sm";
  title?: string;
  role?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={`status-badge status-${tone}${size === "sm" ? " status-badge-sm" : ""}`}
      title={title}
      role={role}
    >
      {glyph !== undefined ? (
        <span className="status-dot" aria-hidden="true">{glyph}</span>
      ) : null}
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const value = status.toLowerCase();
  const tone: BadgeTone = success.has(value)
    ? "success"
    : danger.has(value)
      ? "danger"
      : warning.has(value)
        ? "warning"
        : info.has(value)
          ? "info"
          : "neutral";
  const symbol = tone === "success" ? "✓" : tone === "danger" ? "×"
    : tone === "warning" ? "?" : tone === "info" ? "•" : "–";
  return (
    <StatusPill tone={tone} glyph={symbol}>
      {statusLabel(status)}
    </StatusPill>
  );
}

export function TestStatusBadge({ status }: { status: TestRunStatus }) {
  return <StatusBadge status={status} />;
}

export function OutcomeBadge({ outcome }: { outcome: JourneyOutcome }) {
  return <StatusBadge status={outcome} />;
}

export function SeverityBadge({ severity }: { severity: FindingSeverity }) {
  return <StatusBadge status={severity} />;
}

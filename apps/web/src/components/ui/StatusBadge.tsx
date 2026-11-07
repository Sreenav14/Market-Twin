import type {
  FindingSeverity,
  TestRunStatus,
} from "../../lib/api";
import { statusEntry, type StatusSource, type StatusTone } from "../../lib/status";

export type BadgeTone = "success" | "danger" | "warning" | "info" | "neutral";

// The badge tones are a rendering of the canonical status tones from
// lib/status.ts — one vocabulary of words (statusEntry), two tone sets
// (concept pills use the status tones directly; these CSS classes are the
// signed-in set the sheets already style).
const BADGE_TONES: Record<StatusTone, BadgeTone> = {
  works: "success",
  broken: "danger",
  couldnot: "warning",
  info: "info",
  notchecked: "neutral",
};

const BADGE_GLYPHS: Record<BadgeTone, string> = {
  success: "✓",
  danger: "×",
  warning: "?",
  info: "•",
  neutral: "–",
};

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

/**
 * The one badge component (examination X-1): the word and tone always come
 * from lib/status.ts `statusEntry` for the badge's declared source — never
 * from the caller's raw string. Callers pick the wrapper for their data
 * (run, journey outcome, execution, severity) or pass `source` explicitly.
 */
export function StatusBadge({
  status,
  source = "lifecycle",
}: {
  status: string;
  source?: StatusSource;
}) {
  const entry = statusEntry(source, status);
  const tone = BADGE_TONES[entry.tone];
  return (
    <StatusPill tone={tone} glyph={BADGE_GLYPHS[tone]}>
      {entry.word}
    </StatusPill>
  );
}

export function TestStatusBadge({ status }: { status: TestRunStatus }) {
  return <StatusBadge status={status} source="run" />;
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  return <StatusBadge status={outcome} source="journeyOutcome" />;
}

export function ExecutionBadge({ status }: { status: string }) {
  return <StatusBadge status={status} source="journeyExecution" />;
}

export function SeverityBadge({ severity }: { severity: FindingSeverity }) {
  return <StatusBadge status={severity} source="severity" />;
}

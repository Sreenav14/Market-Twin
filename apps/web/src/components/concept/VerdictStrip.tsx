import React from "react";

export interface TestHistorySegment {
  dateLabel: string;
  verdict: string | null;
  status?: string;
  isFinished: boolean;
}

interface VerdictStripProps {
  appName: string;
  segments: TestHistorySegment[];
  lastTestDate?: string;
  className?: string;
}

export const VerdictStrip: React.FC<VerdictStripProps> = ({
  appName,
  segments,
  lastTestDate,
  className = "",
}) => {
  const ariaDescription = `${appName} test history: ${segments
    .map((s) =>
      s.verdict
        ? `${s.dateLabel}, ${s.verdict}`
        : `${s.dateLabel}, stopped early, no verdict`
    )
    .join(". ")}.`;

  return (
    <div
      role="img"
      aria-label={ariaDescription}
      className={`concept-verdict-strip ${className}`}
      style={{ width: "100%" }}
    >
      <div
        className="flex items-center gap-1"
        style={{ height: "8px", width: "100%", marginBottom: "8px" }}
      >
        {segments.map((seg, idx) => (
          <div
            key={idx}
            style={{
              flex: 1,
              height: "8px",
              borderRadius: "4px",
              minWidth: "16px",
              backgroundColor: seg.isFinished
                ? "var(--flame-deep)"
                : "var(--notchecked-tint)",
              border: seg.isFinished ? "none" : "1px solid var(--line)",
            }}
          />
        ))}
      </div>
      {/* Captions decode each segment: date, and the verdict word or why there is none */}
      <div className="flex gap-1" aria-hidden="true">
        {segments.map((seg, idx) => (
          <div key={idx} style={{ flex: 1, minWidth: "16px" }} className="font-body-small">
            <span style={{ color: "var(--ink-2)" }}>{seg.dateLabel}</span>
            {seg.verdict ? (
              <span style={{ color: "var(--ink)", fontWeight: 600 }}> · {seg.verdict}.</span>
            ) : (
              <span style={{ color: "var(--ink-2)" }}> · Stopped early, no verdict.</span>
            )}
          </div>
        ))}
      </div>
      {lastTestDate && (
        <span className="sr-only">Last test: {lastTestDate}</span>
      )}
    </div>
  );
};

import React from "react";
import { ConceptTotals, formatCoverageAriaLabel, formatCoverageHeadline } from "../../lib/concept-dataset";

interface CoverageBarProps {
  totals: ConceptTotals;
  headline?: string;
  className?: string;
}

export const CoverageBar: React.FC<CoverageBarProps> = ({
  totals,
  headline,
  className = "",
}) => {
  const displayHeadline = headline || formatCoverageHeadline(totals.checked, totals.worked);
  const ariaLabel = formatCoverageAriaLabel(totals);

  const totalAttempts = totals.attempts || 1;
  const pctWorked = (totals.worked / totalAttempts) * 100;
  const pctBroken = (totals.broken / totalAttempts) * 100;
  const pctCouldNot = (totals.couldNotCheck / totalAttempts) * 100;
  const pctNotChecked = (totals.notChecked / totalAttempts) * 100;

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      className={`concept-coverage-container ${className}`}
      style={{ width: "100%" }}
    >
      <div
        className="font-body"
        style={{
          fontWeight: 600,
          color: "var(--ink)",
          marginBottom: "12px",
        }}
      >
        {displayHeadline}
      </div>

      <div
        aria-hidden="true"
        style={{
          height: "14px",
          borderRadius: "7px",
          width: "100%",
          display: "flex",
          overflow: "hidden",
          marginBottom: "12px",
        }}
      >
        {pctWorked > 0 && (
          <div
            style={{
              width: `${pctWorked}%`,
              backgroundColor: "var(--works)",
              height: "100%",
            }}
          />
        )}
        {pctBroken > 0 && (
          <div
            style={{
              width: `${pctBroken}%`,
              backgroundColor: "var(--broken)",
              height: "100%",
            }}
          />
        )}
        {pctCouldNot > 0 && (
          <div
            style={{
              width: `${pctCouldNot}%`,
              backgroundColor: "var(--couldnot)",
              height: "100%",
            }}
          />
        )}
        {pctNotChecked > 0 && (
          <div
            style={{
              width: `${pctNotChecked}%`,
              backgroundColor: "var(--notchecked)",
              height: "100%",
            }}
          />
        )}
      </div>

      {/* One signal per state in the legend: the status glyph in its status
          colour plus the word and count. The bar above already carries the
          colour blocks; squares and dot separators here only repeated it. */}
      <div
        className="flex flex-wrap items-center gap-x-5 gap-y-2 font-grid-cell"
        style={{ fontSize: "13px", color: "var(--ink)" }}
        aria-hidden="true"
      >
        <span className="inline-flex items-center gap-1.5">
          <span style={{ fontWeight: 600, color: "var(--works)" }}>✓</span>
          <span style={{ fontWeight: 600 }}>Worked</span>
          <span>{totals.worked}</span>
        </span>

        <span className="inline-flex items-center gap-1.5">
          <span style={{ fontWeight: 600, color: "var(--broken)" }}>✕</span>
          <span style={{ fontWeight: 600 }}>Broken</span>
          <span>{totals.broken}</span>
        </span>

        <span className="inline-flex items-center gap-1.5">
          <span style={{ fontWeight: 600, color: "var(--couldnot)" }}>?</span>
          <span style={{ fontWeight: 600 }}>Could not check</span>
          <span>{totals.couldNotCheck}</span>
        </span>

        <span className="inline-flex items-center gap-1.5">
          <span style={{ fontWeight: 600, color: "var(--notchecked)" }}>–</span>
          <span style={{ fontWeight: 600 }}>Not checked</span>
          <span>{totals.notChecked}</span>
        </span>
      </div>
    </div>
  );
};

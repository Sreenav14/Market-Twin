import React from "react";
import { ConceptTotals, formatCoverageAriaLabel, formatCoverageHeadline } from "../../lib/concept-dataset";

interface OutcomeCoverageBarProps {
  totals: ConceptTotals;
  headline?: string;
  className?: string;
}

export const OutcomeCoverageBar: React.FC<OutcomeCoverageBarProps> = ({
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

      <div className="rf-bar" aria-hidden="true" style={{ marginBottom: "12px" }}>
        {pctWorked > 0 && <div className="rf-seg rf-seg-works" style={{ flexGrow: totals.worked }} />}
        {pctBroken > 0 && <div className="rf-seg rf-seg-broken" style={{ flexGrow: totals.broken }} />}
        {pctCouldNot > 0 && <div className="rf-seg rf-seg-couldnot" style={{ flexGrow: totals.couldNotCheck }} />}
        {pctNotChecked > 0 && <div className="rf-seg rf-seg-info" style={{ flexGrow: totals.notChecked }} />}
      </div>

      {/* One signal per state in the legend: the status glyph in its status
          colour plus the word and count. The bar above already carries the
          colour blocks; squares and dot separators here only repeated it. */}
      <div
        className="rf-labels font-grid-cell"
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

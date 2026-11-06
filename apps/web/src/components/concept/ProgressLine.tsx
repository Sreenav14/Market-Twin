import React from "react";

interface ProgressLineProps {
  appName?: string;
  checkedAttempts: number;
  totalAttempts: number;
  metaText?: string;
  line1Override?: string;
  onClick?: () => void;
  className?: string;
}

export const ProgressLine: React.FC<ProgressLineProps> = ({
  appName,
  checkedAttempts,
  totalAttempts,
  metaText,
  line1Override,
  onClick,
  className = "",
}) => {
  const lineText =
    line1Override ||
    (appName
      ? `${appName} — testing now · Checked ${checkedAttempts} of ${totalAttempts} attempts`
      : `Checked ${checkedAttempts} of ${totalAttempts} attempts`);

  const fraction = totalAttempts > 0 ? Math.min(1, checkedAttempts / totalAttempts) : 0;
  const pct = Math.round(fraction * 100);

  const content = (
    <div
      role="img"
      aria-label={lineText}
      className={`concept-progress-line ${className}`}
      style={{ width: "100%" }}
    >
      <div
        className="flex items-center justify-between font-body"
        style={{ color: "var(--ink)", marginBottom: "8px" }}
      >
        <span>{lineText}</span>
        {metaText && (
          <span
            className="font-meta-label"
            style={{ color: "var(--ink-faint)", marginLeft: "16px" }}
          >
            {metaText}
          </span>
        )}
      </div>

      {/* Same bar family as the results-page CoverageBar: 14px rounded bar,
          neutral not-checked tone for the portion done (its outcome split is
          not published mid-run, so no outcome colour is claimed). */}
      <div
        aria-hidden="true"
        style={{
          height: "14px",
          borderRadius: "7px",
          backgroundColor: "var(--notchecked-tint)",
          width: "100%",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${pct}%`,
            backgroundColor: "var(--notchecked)",
            borderRadius: "7px",
          }}
        />
      </div>
    </div>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="w-full text-left"
        style={{
          background: "none",
          border: "none",
          padding: "12px 16px",
          borderRadius: "10px",
          cursor: "pointer",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--paper)")}
        onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
      >
        {content}
      </button>
    );
  }

  return content;
};

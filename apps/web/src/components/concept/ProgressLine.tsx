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

      {/* Progress recipe (display.css §8): the portion done in the neutral
          not-checked tone — its outcome split is not published mid-run,
          so no outcome colour is claimed. Fill by scaleX, not width. */}
      <div className="progress" aria-hidden="true" style={{ height: "14px" }}>
        <div
          className="progress-fill"
          style={{ transform: `scaleX(${fraction})`, backgroundColor: "var(--notchecked)" }}
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

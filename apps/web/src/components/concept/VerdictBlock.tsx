import React from "react";

interface VerdictBlockProps {
  word: string;
  reason: string;
  honestInputs?: string;
  isH1?: boolean;
  compact?: boolean;
  className?: string;
}

export const VerdictBlock: React.FC<VerdictBlockProps> = ({
  word,
  reason,
  honestInputs,
  isH1 = true,
  compact = false,
  className = "",
}) => {
  return (
    <section
      className={`concept-card ${className}`}
      style={{
        backgroundColor: "var(--card)",
        border: "1px solid var(--line)",
        borderRadius: "10px",
        padding: compact ? "20px" : "24px",
        boxShadow: "var(--shadow-soft)",
      }}
      aria-label="Verdict"
    >
      <div
        className="font-meta-label"
        style={{ color: "var(--ink-faint)", marginBottom: "8px" }}
      >
        VERDICT
      </div>

      {isH1 ? (
        <h1
          className={compact ? "font-h2-marketing" : "font-verdict-word"}
          style={{
            color: "var(--ink)",
            margin: "0 0 12px 0",
          }}
        >
          {word}
        </h1>
      ) : (
        <h2
          className={compact ? "font-h2-marketing" : "font-verdict-word"}
          style={{
            color: "var(--ink)",
            margin: "0 0 12px 0",
          }}
        >
          {word}
        </h2>
      )}

      <p
        className="font-body"
        style={{ color: "var(--ink-2)", margin: "0 0 16px 0", maxWidth: "68ch" }}
      >
        {reason}
      </p>

      {honestInputs && (
        <div
          className="font-meta-label"
          style={{
            borderTop: "1px solid var(--line)",
            paddingTop: "12px",
            color: "var(--ink-2)",
          }}
        >
          {honestInputs}
        </div>
      )}
    </section>
  );
};

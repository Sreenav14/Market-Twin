import React, { useId, useState } from "react";

interface StepListProps {
  steps?: string[];
  failedStepIndex?: number; // 1-indexed e.g. 6
  mode?: "finished-report" | "watch-live-maya" | "watch-live-tom";
  className?: string;
}

export const StepList: React.FC<StepListProps> = ({
  steps = [
    "Opened the store",
    "Found a t-shirt",
    "Chose size and colour",
    "Added it to her bag",
    "Went to checkout",
    "Clicked Pay — nothing happened",
    "Gave up and left",
  ],
  failedStepIndex = 6,
  mode = "finished-report",
  className = "",
}) => {
  const listId = useId();
  const [expanded, setExpanded] = useState(false);

  // Watch live mode for Tom: ONE line only
  if (mode === "watch-live-tom") {
    return (
      <div
        className={`font-grid-cell ${className}`}
        style={{
          color: "var(--ink-2)",
          padding: "8px 0",
          fontWeight: 400,
        }}
      >
        <span style={{ color: "var(--works)", marginRight: "6px" }}>✓</span>
        <span>All 6 attempts · Done</span>
      </div>
    );
  }

  // Watch live mode for Maya: steps 1-4 collapsed with toggle + current step 5
  if (mode === "watch-live-maya") {
    const completedSteps = steps.slice(0, 4);
    const currentStep = steps[4] || "Went to checkout";

    return (
      <div className={`concept-steplist-live ${className}`}>
        {/* Collapsed summary line + toggle */}
        <div
          className="flex items-center justify-between"
          style={{
            borderBottom: "1px solid var(--line)",
            padding: "8px 0",
          }}
        >
          <div className="font-grid-cell" style={{ color: "var(--ink-2)" }}>
            <span style={{ color: "var(--works)", marginRight: "6px" }}>✓</span>
            <span>Steps 1–4 · Done</span>
          </div>

          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={listId}
            onClick={() => setExpanded(!expanded)}
            className="font-button-label"
            style={{
              minHeight: "44px",
              padding: "8px 12px",
              backgroundColor: "transparent",
              border: "none",
              color: "var(--ink)",
              cursor: "pointer",
              textDecoration: "underline",
            }}
          >
            {expanded ? "Hide steps" : "Show steps"}
          </button>
        </div>

        {/* Expanded 1-4 steps region */}
        {expanded && (
          <ol
            id={listId}
            style={{
              margin: 0,
              padding: "4px 0",
              listStyle: "none",
            }}
          >
            {completedSteps.map((stepName, idx) => (
              <li
                key={idx}
                className="font-grid-cell flex items-center gap-2"
                style={{
                  padding: "6px 0",
                  color: "var(--ink-2)",
                  borderBottom: "1px solid var(--line)",
                }}
              >
                <span className="font-mono-data" style={{ color: "var(--ink-faint)", width: "24px" }}>
                  {idx + 1}.
                </span>
                <span style={{ color: "var(--works)", marginRight: "4px" }}>✓</span>
                <span>{stepName}</span>
              </li>
            ))}
          </ol>
        )}

        {/* Current active step (step 5) */}
        <div
          className="font-grid-cell flex items-center gap-2"
          style={{
            padding: "8px 0",
            color: "var(--ink)",
            fontWeight: 600,
          }}
        >
          <span className="font-mono-data" style={{ color: "var(--ink-faint)", width: "24px" }}>
            5.
          </span>
          <span style={{ marginRight: "4px" }}>◐</span>
          <span>{currentStep}</span>
        </div>
      </div>
    );
  }

  // Full finished report mode: all steps rendered, failed step highlighted with ✕ Broken
  return (
    <ol
      className={`concept-steplist-report ${className}`}
      style={{
        margin: 0,
        padding: 0,
        listStyle: "none",
      }}
    >
      {steps.map((stepName, idx) => {
        const stepNum = idx + 1;
        const isFailed = stepNum === failedStepIndex;

        return (
          <li
            key={idx}
            className="font-grid-cell flex items-center gap-2"
            style={{
              padding: "8px 0",
              borderBottom: idx < steps.length - 1 ? "1px solid var(--line)" : "none",
              color: isFailed ? "var(--broken)" : "var(--ink-2)",
              fontWeight: isFailed ? 600 : 400,
            }}
          >
            <span
              className="font-mono-data"
              style={{
                color: isFailed ? "var(--broken)" : "var(--ink-faint)",
                width: "24px",
              }}
            >
              {stepNum}.
            </span>
            <span
              style={{
                color: isFailed ? "var(--broken)" : "var(--works)",
                fontWeight: 600,
                marginRight: "4px",
              }}
            >
              {isFailed ? "✕" : "✓"}
            </span>
            <span>{stepName}</span>
          </li>
        );
      })}
    </ol>
  );
};

import React from "react";

interface ProofStepThumbnail {
  stepNumber: number;
  label?: string;
}

interface ProofTrailProps {
  totalScreenshots?: number | null;
  testerName?: string;
  steps?: ProofStepThumbnail[];
  className?: string;
}

export const ProofTrail: React.FC<ProofTrailProps> = ({
  totalScreenshots,
  testerName = "Maya",
  steps = [
    { stepNumber: 5, label: "STEP 5" },
    { stepNumber: 6, label: "STEP 6" },
    { stepNumber: 7, label: "STEP 7" },
  ],
  className = "",
}) => {
  const shownCount = Math.min(steps.length, 3);
  const displaySteps = steps.slice(0, 3);
  const remaining =
    typeof totalScreenshots === "number" && totalScreenshots > shownCount
      ? totalScreenshots - shownCount
      : 0;

  const ariaLabel =
    typeof totalScreenshots === "number"
      ? `${totalScreenshots} screenshots, ${shownCount} shown`
      : `Screenshots from ${testerName}'s attempt (${shownCount} shown)`;

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      className={`concept-proof-trail flex items-center gap-2 ${className}`}
      style={{ marginTop: "8px" }}
    >
      <div className="flex items-center gap-2" aria-hidden="true">
        {displaySteps.map((s, idx) => (
          <div key={idx} className="flex flex-col items-center">
            <div
              style={{
                width: "56px",
                height: "36px",
                borderRadius: "6px",
                border: "1px solid var(--line)",
                backgroundColor: "var(--paper)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                overflow: "hidden",
                position: "relative",
              }}
            >
              {/* Mini mock wireframe sketch */}
              <div
                style={{
                  width: "44px",
                  height: "24px",
                  border: "1px solid var(--line)",
                  borderRadius: "2px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "2px",
                  padding: "2px",
                }}
              >
                <div
                  style={{
                    height: "4px",
                    width: "70%",
                    backgroundColor: "var(--line)",
                    borderRadius: "1px",
                  }}
                />
                <div
                  style={{
                    height: "3px",
                    width: "50%",
                    backgroundColor: "var(--line)",
                    borderRadius: "1px",
                  }}
                />
              </div>
            </div>
            <span
              className="font-meta-label"
              style={{
                fontSize: "11px",
                lineHeight: "16px",
                color: "var(--ink-faint)",
                marginTop: "4px",
              }}
            >
              {s.label || `STEP ${s.stepNumber}`}
            </span>
          </div>
        ))}
      </div>

      {remaining > 0 && (
        <span
          className="font-mono-data"
          style={{
            fontSize: "12px",
            lineHeight: "18px",
            color: "var(--ink-2)",
            marginLeft: "4px",
          }}
          aria-hidden="true"
        >
          +{remaining} more
        </span>
      )}
    </div>
  );
};

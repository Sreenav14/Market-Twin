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

/**
 * The evidence slot under a problem card. This sample report has no real
 * captured frames to show, so the slot is an honest labelled panel in the
 * house style — it names the steps the proof covers and says plainly that
 * the frames themselves are not part of the sample, instead of drawing
 * fake wireframe "screenshots" (Hallmark P2-21).
 */
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
      ? `Sample evidence: ${totalScreenshots} screenshots from ${testerName}'s attempt, frames not shown in this sample`
      : `Sample evidence from ${testerName}'s attempt, frames not shown in this sample`;

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      className={`concept-proof-trail ${className}`}
      style={{
        marginTop: "12px",
        backgroundColor: "var(--paper)",
        border: "1px solid var(--line)",
        borderRadius: "10px",
        padding: "12px",
      }}
    >
      <div
        className="font-meta-label"
        style={{ color: "var(--ink-faint)", marginBottom: "8px" }}
        aria-hidden="true"
      >
        SAMPLE EVIDENCE
      </div>

      {typeof totalScreenshots === "number" ? (
        <>
          <div className="flex flex-wrap items-stretch gap-2" aria-hidden="true">
            {displaySteps.map((s, idx) => (
              <div
                key={idx}
                style={{
                  width: "104px",
                  border: "1px solid var(--line)",
                  borderRadius: "6px",
                  backgroundColor: "var(--card)",
                  padding: "8px",
                }}
              >
                <div
                  className="font-meta-label"
                  style={{ color: "var(--ink)", marginBottom: "4px" }}
                >
                  {s.label || `STEP ${s.stepNumber}`}
                </div>
                <div
                  className="font-body-small"
                  style={{ color: "var(--ink-faint)", fontSize: "12px", lineHeight: "16px" }}
                >
                  Sample frame, not shown
                </div>
              </div>
            ))}
            {remaining > 0 && (
              <div
                className="font-mono-data"
                style={{
                  fontSize: "12px",
                  lineHeight: "18px",
                  color: "var(--ink-2)",
                  alignSelf: "center",
                  marginLeft: "4px",
                }}
              >
                +{remaining} more
              </div>
            )}
          </div>
          <p
            className="font-body-small"
            style={{ color: "var(--ink-2)", margin: "8px 0 0" }}
            aria-hidden="true"
          >
            {totalScreenshots} screenshots were captured for this problem. The
            frames themselves are not part of this sample report.
          </p>
        </>
      ) : (
        <p
          className="font-body-small"
          style={{ color: "var(--ink-2)", margin: 0 }}
          aria-hidden="true"
        >
          Proof is attached to this problem. The frames themselves are not
          part of this sample report.
        </p>
      )}
    </div>
  );
};

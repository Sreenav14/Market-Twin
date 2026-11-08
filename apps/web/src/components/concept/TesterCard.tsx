import React, { useState } from "react";
import { StepList } from "./StepList";
import { Avatar } from "../ui/Avatar";
import { TakeoverPanel } from "./TakeoverPanel";

export interface TesterCardData {
  id: "tom" | "maya" | "priya" | string;
  name: string;
  label: "Expert" | "First-time user" | "Impatient mobile user" | string;
  colour: string;
  state: "finished" | "doing" | "needs-help";
  activityText: string;
  progressText?: string;
  waitingText?: string;
  frameAriaLabel: string;
  frameContent: React.ReactNode;
}

interface TesterCardProps {
  tester: TesterCardData;
  className?: string;
}

export const TesterCard: React.FC<TesterCardProps> = ({ tester, className = "" }) => {
  const [inOwnerControl, setInOwnerControl] = useState(false);

  return (
    <article
      className={`concept-tester-card flex flex-col justify-between ${className}`}
      style={{
        backgroundColor: "var(--card)",
        border: "1px solid var(--line)",
        borderRadius: "10px",
        padding: "20px",
        boxShadow: "var(--shadow-soft)",
      }}
      aria-label={`${tester.name}'s test session`}
    >
      <div>
        {/* Header row */}
        <div className="flex items-center gap-3" style={{ marginBottom: "12px" }}>
          <Avatar kind="persona" name={tester.name} tint={tester.colour} />
          <div>
            <h3 className="font-h3" style={{ color: "var(--ink)", margin: 0 }}>
              {tester.name}
            </h3>
            <div className="font-body-small" style={{ color: "var(--ink-2)" }}>
              {tester.label}
            </div>
          </div>
        </div>

        {/* State line */}
        <div
          className="font-grid-cell flex items-center gap-1.5"
          style={{
            fontWeight: 600,
            color: "var(--ink)",
            marginBottom: "8px",
          }}
        >
          {tester.state === "finished" && (
            <>
              <span style={{ color: "var(--works)" }}>✓</span>
              <span>Finished</span>
            </>
          )}
          {tester.state === "doing" && (
            <>
              <span>◐</span>
              <span>Doing</span>
            </>
          )}
          {tester.state === "needs-help" && (
            <>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: "14px",
                  height: "14px",
                  borderRadius: "50%",
                  border: "1px solid var(--ink)",
                  fontSize: "10px",
                  fontWeight: 600,
                  color: "var(--ink)",
                }}
              >
                !
              </span>
              <span>Needs your help</span>
            </>
          )}
        </div>

        {/* Activity line */}
        <div
          className="font-body-small"
          style={{ color: "var(--ink)", marginBottom: "8px" }}
        >
          {tester.activityText}
        </div>

        {/* Plain-words progress or waiting line */}
        {tester.progressText && (
          <div
            className="font-body-small"
            style={{ color: "var(--ink-2)", marginBottom: "12px" }}
          >
            {tester.progressText}
          </div>
        )}
        {tester.waitingText && (
          <div
            className="font-body-small"
            style={{ color: "var(--ink-2)", marginBottom: "12px" }}
          >
            {tester.waitingText}
          </div>
        )}

        {/* Browser frame mock */}
        <div
          role="img"
          aria-label={inOwnerControl ? "Your view of the browser" : tester.frameAriaLabel}
          style={{
            width: "100%",
            borderRadius: "6px",
            border: "1px solid var(--line)",
            backgroundColor: "var(--paper)",
            overflow: "hidden",
            marginBottom: "12px",
            position: "relative",
          }}
        >
          {/* Frame top bar */}
          <div
            className="flex items-center justify-between"
            style={{
              padding: "6px 12px",
              backgroundColor: "var(--card)",
              borderBottom: "1px solid var(--line)",
            }}
          >
            <span
              className="font-meta-label"
              style={{ color: "var(--ink-faint)" }}
            >
              {inOwnerControl ? "YOUR VIEW" : `${tester.name.toUpperCase()}'S VIEW`}
            </span>
          </div>

          {/* Frame content */}
          <div style={{ padding: "16px", minHeight: "130px" }}>
            {tester.frameContent}
          </div>
        </div>

        {/* Step list / attempts line */}
        {tester.id === "tom" && <StepList mode="watch-live-tom" />}
        {tester.id === "maya" && <StepList mode="watch-live-maya" />}
      </div>

      {/* Takeover panel for blocked tester */}
      {tester.state === "needs-help" && (
        <TakeoverPanel
          testerName={tester.name}
          taskName="Track an order"
          onControlChange={(control) => setInOwnerControl(control)}
        />
      )}
    </article>
  );
};

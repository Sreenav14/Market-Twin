import React from "react";

interface NeedsYouRowProps {
  testerName?: string;
  taskName?: string;
  waitingMinutes?: number;
  testerColour?: string;
  onHelpClick?: () => void;
  className?: string;
}

export const NeedsYouRow: React.FC<NeedsYouRowProps> = ({
  testerName = "Priya",
  taskName = "Track an order",
  waitingMinutes = 6,
  testerColour = "var(--priya)",
  onHelpClick,
  className = "",
}) => {
  const initial = testerName.charAt(0);

  return (
    <div
      className={`concept-needs-you-row flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${className}`}
      style={{
        padding: "16px 20px",
        backgroundColor: "var(--card)",
        border: "1px solid var(--line)",
        borderRadius: "10px",
        boxShadow: "var(--shadow-soft)",
      }}
    >
      <div className="flex items-center gap-3">
        {/* Avatar 24px */}
        <div
          style={{
            width: "24px",
            height: "24px",
            borderRadius: "50%",
            backgroundColor: testerColour,
            color: "var(--ink-on-dark)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "11px",
            fontWeight: 600,
            flexShrink: 0,
          }}
          aria-hidden="true"
        >
          {initial}
        </div>

        {/* Text block */}
        <div>
          <div
            className="font-body flex items-center gap-1.5"
            style={{ fontWeight: 600, color: "var(--ink)" }}
          >
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: "16px",
                height: "16px",
                borderRadius: "50%",
                border: "1.5px solid var(--ink)",
                fontSize: "11px",
                fontWeight: 600,
                color: "var(--ink)",
              }}
              aria-hidden="true"
            >
              !
            </span>
            <span>
              {testerName} is stuck logging in — {taskName}
            </span>
          </div>

          <div
            className="font-body-small"
            style={{ color: "var(--ink-2)", marginTop: "2px" }}
          >
            Waiting {waitingMinutes} minutes
          </div>
        </div>
      </div>

      {/* Button: Help {Name} — the urgent action is the page's filled primary */}
      <button
        type="button"
        onClick={onHelpClick}
        className="font-button-label transition-colors w-full sm:w-auto"
        style={{
          minHeight: "44px",
          padding: "12px 20px",
          borderRadius: 0,
          backgroundColor: "var(--flame-deep)",
          border: "1px solid var(--flame-deep)",
          color: "var(--ink-on-dark)",
          cursor: "pointer",
          whiteSpace: "nowrap",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--flame-deep-hover)")}
        onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "var(--flame-deep)")}
      >
        Help {testerName}
      </button>
    </div>
  );
};

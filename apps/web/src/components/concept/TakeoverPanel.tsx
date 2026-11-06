import React, { useRef, useState } from "react";

interface TakeoverPanelProps {
  testerName?: string;
  taskName?: string;
  onControlChange?: (inControl: boolean) => void;
  className?: string;
}

export const TakeoverPanel: React.FC<TakeoverPanelProps> = ({
  testerName = "Priya",
  taskName = "Track an order",
  onControlChange,
  className = "",
}) => {
  const [inControl, setInControl] = useState(false);
  const titleBRef = useRef<HTMLHeadingElement | null>(null);
  const buttonARef = useRef<HTMLButtonElement | null>(null);

  const handleTakeover = () => {
    setInControl(true);
    if (onControlChange) onControlChange(true);
    setTimeout(() => {
      titleBRef.current?.focus();
    }, 50);
  };

  const handleHandBack = () => {
    setInControl(false);
    if (onControlChange) onControlChange(false);
    setTimeout(() => {
      buttonARef.current?.focus();
    }, 50);
  };

  return (
    <div
      className={`concept-takeover-panel ${className}`}
      style={{
        borderTop: "1px solid var(--line)",
        paddingTop: "16px",
        marginTop: "16px",
      }}
    >
      {!inControl ? (
        // State A: idle / waiting
        <div>
          <h3
            className="font-h3"
            style={{ color: "var(--ink)", margin: "0 0 8px 0" }}
          >
            {testerName} needs your help
          </h3>
          <p
            className="font-body-small"
            style={{ color: "var(--ink-2)", margin: "0 0 16px 0" }}
          >
            Log in to {testerName}&apos;s test browser to unblock {taskName}.
          </p>
          <button
            ref={buttonARef}
            type="button"
            aria-pressed="false"
            onClick={handleTakeover}
            className="font-button-label transition-colors w-full sm:w-auto"
            style={{
              minHeight: "44px",
              padding: "12px 20px",
              borderRadius: 0,
              backgroundColor: "var(--flame-deep)",
              color: "var(--ink-on-dark)",
              border: "1px solid var(--flame-deep)",
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--flame-deep-hover)")}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "var(--flame-deep)")}
          >
            Take over {testerName}&apos;s browser
          </button>
        </div>
      ) : (
        // State B: owner in control
        <div>
          <h3
            ref={titleBRef}
            tabIndex={-1}
            className="font-h3"
            style={{ color: "var(--ink)", margin: "0 0 8px 0", outline: "none" }}
          >
            You are in control
          </h3>
          <p
            className="font-body-small"
            style={{ color: "var(--ink-2)", margin: "0 0 16px 0" }}
          >
            You are using {testerName}&apos;s test browser. {testerName} is paused.
          </p>
          <button
            type="button"
            aria-pressed="true"
            onClick={handleHandBack}
            className="font-button-label transition-colors w-full sm:w-auto"
            style={{
              minHeight: "44px",
              padding: "12px 20px",
              borderRadius: 0,
              backgroundColor: "var(--flame-deep)",
              color: "var(--ink-on-dark)",
              border: "1px solid var(--flame-deep)",
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--flame-deep-hover)")}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "var(--flame-deep)")}
          >
            Hand back to {testerName}
          </button>
        </div>
      )}
    </div>
  );
};

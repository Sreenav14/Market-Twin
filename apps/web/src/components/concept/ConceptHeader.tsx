import React from "react";
import { MegaMenu } from "./MegaMenu";

interface ConceptHeaderProps {
  onNavigate?: (destination: string) => void;
  onSignIn?: () => void;
  onStartTest?: () => void;
  className?: string;
}

export const ConceptHeader: React.FC<ConceptHeaderProps> = ({
  onNavigate,
  onSignIn,
  onStartTest,
  className = "",
}) => {
  return (
    <header
      className={`concept-marketing-header w-full flex items-center justify-between ${className}`}
      style={{
        height: "64px",
        backgroundColor: "var(--paper)",
        borderBottom: "1px solid var(--line)",
        paddingLeft: "24px",
        paddingRight: "24px",
      }}
    >
      {/* Left: Logo wordmark */}
      <div className="flex items-center gap-6">
        <button
          type="button"
          onClick={() => onNavigate && onNavigate("Landing page")}
          className="text-left font-sans cursor-pointer"
          style={{
            fontSize: "18px",
            lineHeight: "24px",
            fontWeight: 650,
            color: "var(--ink)",
            background: "none",
            border: "none",
            padding: 0,
          }}
        >
          MarketTwin
        </button>

        {/* Center / Left Nav */}
        <nav
          aria-label="Main Navigation"
          className="hidden md:flex items-center gap-6"
        >
          <MegaMenu onNavigate={onNavigate} />

          <button
            type="button"
            onClick={() => onNavigate && onNavigate("How it works")}
            className="font-button-label transition-colors hidden lg:block"
            style={{
              minHeight: "44px",
              padding: "8px 12px",
              whiteSpace: "nowrap",
              background: "none",
              border: "none",
              color: "var(--ink)",
              cursor: "pointer",
            }}
          >
            HOW IT WORKS
          </button>

          <button
            type="button"
            onClick={() => onNavigate && onNavigate("Example report")}
            className="font-button-label transition-colors hidden lg:block"
            style={{
              minHeight: "44px",
              padding: "8px 12px",
              whiteSpace: "nowrap",
              background: "none",
              border: "none",
              color: "var(--ink)",
              cursor: "pointer",
            }}
          >
            EXAMPLE REPORT
          </button>
        </nav>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={onSignIn}
          className="font-button-label transition-colors"
          style={{
            minHeight: "44px",
            padding: "8px 16px",
            whiteSpace: "nowrap",
            background: "none",
            border: "none",
            color: "var(--ink)",
            cursor: "pointer",
          }}
        >
          SIGN IN
        </button>

        <button
          type="button"
          onClick={onStartTest}
          className="font-button-label transition-colors"
          style={{
            minHeight: "44px",
            padding: "12px 20px",
            borderRadius: 0,
            backgroundColor: "var(--flame-deep)",
            color: "#FFFFFF",
            border: "none",
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
          onMouseEnter={(e) =>
            (e.currentTarget.style.backgroundColor = "var(--flame-deep-hover)")
          }
          onMouseLeave={(e) =>
            (e.currentTarget.style.backgroundColor = "var(--flame-deep)")
          }
        >
          START A TEST
        </button>
      </div>
    </header>
  );
};

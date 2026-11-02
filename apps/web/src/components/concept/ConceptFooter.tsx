import React from "react";

interface ConceptFooterProps {
  onNavigate?: (destination: string) => void;
  className?: string;
}

export const ConceptFooter: React.FC<ConceptFooterProps> = ({
  onNavigate,
  className = "",
}) => {
  return (
    <footer
      className={`concept-footer w-full ${className}`}
      style={{
        backgroundColor: "var(--footer-deep)",
        paddingTop: "64px",
        color: "#FFFFFF",
      }}
    >
      <div className="concept-marketing-container" style={{ marginBottom: "64px" }}>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-8">
          {/* Brand Col */}
          <div>
            <div
              className="font-sans"
              style={{
                fontSize: "18px",
                lineHeight: "24px",
                fontWeight: 650,
                color: "#FFFFFF",
                marginBottom: "12px",
              }}
            >
              MarketTwin
            </div>
            <p
              className="font-body-small"
              style={{ color: "rgba(255, 255, 255, 0.7)", maxWidth: "240px" }}
            >
              Know if your app is ready — before your customers find out.
            </p>
          </div>

          {/* See it working Col */}
          <div>
            <div
              className="font-meta-label"
              style={{ color: "#FFFFFF", marginBottom: "16px" }}
            >
              SEE IT WORKING
            </div>
            <ul
              className="flex flex-col gap-2.5 font-body-small"
              style={{ listStyle: "none", margin: 0, padding: 0 }}
            >
              {["Dashboard", "Watch live", "Test results", "Testers"].map(
                (item) => (
                  <li key={item}>
                    <button
                      type="button"
                      onClick={() => onNavigate && onNavigate(item)}
                      className="transition-opacity text-left"
                      style={{
                        background: "none",
                        border: "none",
                        color: "rgba(255, 255, 255, 0.7)",
                        padding: 0,
                        cursor: "pointer",
                      }}
                      onMouseEnter={(e) =>
                        (e.currentTarget.style.color = "#FFFFFF")
                      }
                      onMouseLeave={(e) =>
                        (e.currentTarget.style.color = "rgba(255, 255, 255, 0.7)")
                      }
                    >
                      {item}
                    </button>
                  </li>
                )
              )}
            </ul>
          </div>

          {/* Get your answers Col */}
          <div>
            <div
              className="font-meta-label"
              style={{ color: "#FFFFFF", marginBottom: "16px" }}
            >
              GET YOUR ANSWERS
            </div>
            <ul
              className="flex flex-col gap-2.5 font-body-small"
              style={{ listStyle: "none", margin: 0, padding: 0 }}
            >
              {["Example report", "How it works", "Your apps"].map((item) => (
                <li key={item}>
                  <button
                    type="button"
                    onClick={() => onNavigate && onNavigate(item)}
                    className="transition-opacity text-left"
                    style={{
                      background: "none",
                      border: "none",
                      color: "rgba(255, 255, 255, 0.7)",
                      padding: 0,
                      cursor: "pointer",
                    }}
                    onMouseEnter={(e) =>
                      (e.currentTarget.style.color = "#FFFFFF")
                    }
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.color = "rgba(255, 255, 255, 0.7)")
                    }
                  >
                    {item}
                  </button>
                </li>
              ))}
            </ul>
          </div>

          {/* Account Col */}
          <div>
            <div
              className="font-meta-label"
              style={{ color: "#FFFFFF", marginBottom: "16px" }}
            >
              WORKSPACE
            </div>
            <ul
              className="flex flex-col gap-2.5 font-body-small"
              style={{ listStyle: "none", margin: 0, padding: 0 }}
            >
              {["Add an app", "Settings"].map((item) => (
                <li key={item}>
                  <button
                    type="button"
                    onClick={() => onNavigate && onNavigate(item)}
                    className="transition-opacity text-left"
                    style={{
                      background: "none",
                      border: "none",
                      color: "rgba(255, 255, 255, 0.7)",
                      padding: 0,
                      cursor: "pointer",
                    }}
                    onMouseEnter={(e) =>
                      (e.currentTarget.style.color = "#FFFFFF")
                    }
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.color = "rgba(255, 255, 255, 0.7)")
                    }
                  >
                    {item}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* Normative Bottom Bar (§6 item 11, §13 exception) */}
      <div
        className="w-full"
        style={{
          borderTop: "1px solid rgba(255, 255, 255, 0.15)",
          padding: "16px 24px",
        }}
      >
        <div className="concept-marketing-container flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
          <div
            className="font-meta-label"
            style={{
              fontSize: "11px",
              color: "rgba(255, 255, 255, 0.7)",
            }}
          >
            © 2026 MarketTwin · Concept design
          </div>

          <div
            className="font-meta-label"
            style={{
              fontSize: "11px",
              color: "rgba(255, 255, 255, 0.7)",
            }}
          >
            Developed by SJ
          </div>
        </div>
      </div>
    </footer>
  );
};

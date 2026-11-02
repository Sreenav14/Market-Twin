import React from "react";

interface TriptychSignatureProps {
  compact?: boolean;
  className?: string;
}

export const TriptychSignature: React.FC<TriptychSignatureProps> = ({
  compact = false,
  className = "",
}) => {
  const ariaLabel =
    "The same store, seen by three testers. Tom bought it with no trouble. Maya's Pay button did nothing. Priya bought it on her phone, but search kept timing out. Put together, the verdict is: Not ready yet.";

  return (
    <figure
      role={compact ? undefined : "img"}
      aria-label={compact ? undefined : ariaLabel}
      className={`concept-triptych-figure ${className}`}
      style={{ margin: 0, width: "100%" }}
    >
      {/* 3 Panels Row */}
      <div
        className="flex flex-col lg:flex-row items-stretch lg:items-start justify-center gap-6"
        aria-hidden={compact ? undefined : true}
      >
        {/* Tom Panel */}
        <div
          className="triptych-panel flex-1"
          style={{
            backgroundColor: "var(--card)",
            border: "1px solid var(--line)",
            borderTop: "3px solid var(--tom)",
            borderRadius: "10px",
            padding: compact ? "16px" : "20px",
            boxShadow: "var(--shadow-soft)",
            minWidth: 0,
          }}
        >
          <div className="flex items-center gap-3" style={{ marginBottom: compact ? "8px" : "16px" }}>
            <div
              style={{
                width: compact ? "24px" : "40px",
                height: compact ? "24px" : "40px",
                borderRadius: "50%",
                backgroundColor: "var(--tom)",
                color: "#FFFFFF",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 600,
                fontSize: compact ? "11px" : "16px",
                flexShrink: 0,
              }}
            >
              T
            </div>
            <div>
              <div className="font-h3" style={{ fontSize: compact ? "15px" : "18px", color: "var(--ink)" }}>
                Tom
              </div>
              <div className="font-body-small" style={{ fontSize: compact ? "12px" : "14px", color: "var(--ink-2)" }}>
                Expert
              </div>
            </div>
          </div>

          {!compact && (
            <div
              style={{
                padding: "16px",
                borderRadius: "6px",
                border: "1px solid var(--line)",
                backgroundColor: "var(--paper)",
                marginBottom: "16px",
              }}
            >
              <div className="font-meta-label" style={{ color: "var(--ink-faint)", marginBottom: "4px" }}>
                THREAD & CO.
              </div>
              <div className="font-body" style={{ fontWeight: 600, color: "var(--ink)", marginBottom: "8px" }}>
                Classic tee — $28
              </div>
              <div
                style={{
                  border: "1px solid var(--ink)",
                  padding: "8px 16px",
                  display: "inline-block",
                  fontSize: "13px",
                  fontFamily: "IBM Plex Mono, monospace",
                  fontWeight: 600,
                  color: "var(--ink)",
                }}
              >
                Pay $28
              </div>
            </div>
          )}

          <div
            className="font-grid-cell"
            style={{
              fontWeight: 600,
              color: "var(--works)",
              marginBottom: "8px",
            }}
          >
            ✓ Worked — Bought it with no trouble.
          </div>

          <div
            className="font-body-small"
            style={{ color: "var(--ink-2)" }}
          >
            Noticed: search suggestions flicker.
          </div>
        </div>

        {/* Maya Panel */}
        <div
          className="triptych-panel flex-1"
          style={{
            backgroundColor: "var(--card)",
            border: "1px solid var(--line)",
            borderTop: "3px solid var(--maya)",
            borderRadius: "10px",
            padding: compact ? "16px" : "20px",
            boxShadow: "var(--shadow-soft)",
            minWidth: 0,
          }}
        >
          <div className="flex items-center gap-3" style={{ marginBottom: compact ? "8px" : "16px" }}>
            <div
              style={{
                width: compact ? "24px" : "40px",
                height: compact ? "24px" : "40px",
                borderRadius: "50%",
                backgroundColor: "var(--maya)",
                color: "#FFFFFF",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 600,
                fontSize: compact ? "11px" : "16px",
                flexShrink: 0,
              }}
            >
              M
            </div>
            <div>
              <div className="font-h3" style={{ fontSize: compact ? "15px" : "18px", color: "var(--ink)" }}>
                Maya
              </div>
              <div className="font-body-small" style={{ fontSize: compact ? "12px" : "14px", color: "var(--ink-2)" }}>
                First-time user
              </div>
            </div>
          </div>

          {!compact && (
            <div
              style={{
                padding: "16px",
                borderRadius: "6px",
                border: "1px solid var(--line)",
                backgroundColor: "var(--paper)",
                marginBottom: "16px",
              }}
            >
              <div className="font-meta-label" style={{ color: "var(--ink-faint)", marginBottom: "4px" }}>
                THREAD & CO.
              </div>
              <div className="font-body" style={{ fontWeight: 600, color: "var(--ink)", marginBottom: "8px" }}>
                Classic tee — $28
              </div>
              <div
                style={{
                  border: "1px solid var(--ink)",
                  padding: "8px 16px",
                  display: "inline-block",
                  fontSize: "13px",
                  fontFamily: "IBM Plex Mono, monospace",
                  fontWeight: 600,
                  color: "var(--ink)",
                }}
              >
                Pay $28
              </div>
            </div>
          )}

          <div
            className="font-grid-cell"
            style={{
              fontWeight: 600,
              color: "var(--broken)",
              marginBottom: "8px",
            }}
          >
            ✕ Broken — Pay button does nothing.
          </div>

          <div
            className="font-body-small"
            style={{ color: "var(--ink-2)" }}
          >
            &quot;I didn&apos;t know if I&apos;d been charged.&quot;
          </div>
        </div>

        {/* Priya Panel (Phone width: 260px fixed on desktop) */}
        <div
          className="triptych-panel mx-auto lg:mx-0"
          style={{
            width: "100%",
            maxWidth: "260px",
            backgroundColor: "var(--card)",
            border: "1px solid var(--line)",
            borderTop: "3px solid var(--priya)",
            borderRadius: "10px",
            padding: compact ? "16px" : "20px",
            boxShadow: "var(--shadow-soft)",
            flexShrink: 0,
          }}
        >
          <div className="flex items-center gap-3" style={{ marginBottom: compact ? "8px" : "16px" }}>
            <div
              style={{
                width: compact ? "24px" : "40px",
                height: compact ? "24px" : "40px",
                borderRadius: "50%",
                backgroundColor: "var(--priya)",
                color: "#FFFFFF",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 600,
                fontSize: compact ? "11px" : "16px",
                flexShrink: 0,
              }}
            >
              P
            </div>
            <div>
              <div className="font-h3" style={{ fontSize: compact ? "15px" : "18px", color: "var(--ink)" }}>
                Priya
              </div>
              <div className="font-body-small" style={{ fontSize: compact ? "12px" : "14px", color: "var(--ink-2)" }}>
                Impatient mobile user
              </div>
            </div>
          </div>

          {!compact && (
            <div
              style={{
                padding: "16px",
                borderRadius: "6px",
                border: "1px solid var(--line)",
                backgroundColor: "var(--paper)",
                marginBottom: "16px",
              }}
            >
              <div className="font-meta-label" style={{ color: "var(--ink-faint)", marginBottom: "4px" }}>
                THREAD & CO.
              </div>
              <div className="font-body" style={{ fontWeight: 600, color: "var(--ink)", marginBottom: "8px" }}>
                Classic tee — $28
              </div>
              <div
                style={{
                  border: "1px solid var(--ink)",
                  padding: "8px 16px",
                  display: "inline-block",
                  fontSize: "13px",
                  fontFamily: "IBM Plex Mono, monospace",
                  fontWeight: 600,
                  color: "var(--ink)",
                }}
              >
                Pay $28
              </div>
            </div>
          )}

          <div
            className="font-grid-cell"
            style={{
              fontWeight: 600,
              color: "var(--works)",
              marginBottom: "8px",
            }}
          >
            ✓ Worked — Bought it on her phone.
          </div>

          <div
            className="font-body-small"
            style={{ color: "var(--ink-2)" }}
          >
            ? Search kept timing out — couldn&apos;t check it.
          </div>
        </div>
      </div>

      {/* Put Together Strip */}
      <div
        className="w-full flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
        style={{
          marginTop: "24px",
          padding: "20px 24px",
          backgroundColor: "var(--card)",
          border: "1px solid var(--line)",
          borderRadius: "10px",
        }}
        aria-hidden={compact ? undefined : true}
      >
        <div>
          <div
            className="font-meta-label"
            style={{ color: "var(--ink-faint)", marginBottom: "8px" }}
          >
            PUT TOGETHER
          </div>
          <div className="font-body flex flex-col gap-1" style={{ color: "var(--ink)" }}>
            <div>Works — Browsing, sign-up, discount codes</div>
            <div>Broken — Pay button (found by Maya, checked again)</div>
            <div>Couldn&apos;t check — Search, on Priya&apos;s phone</div>
          </div>
        </div>

        <div
          className="font-button-label inline-flex items-center"
          style={{
            backgroundColor: "var(--ink)",
            color: "#FFFFFF",
            padding: "8px 20px",
            borderRadius: "999px",
            whiteSpace: "nowrap",
          }}
        >
          Verdict · Not ready yet
        </div>
      </div>
    </figure>
  );
};

import React from "react";
import {
  CANONICAL_DEMO_DATA,
  ConceptPayload,
} from "../../lib/concept-dataset";
import {
  ContextTabs,
  TesterCard,
  TesterCardData,
} from "../../components/concept";

interface WatchLivePageProps {
  data?: ConceptPayload;
  onNavigate?: (destination: string) => void;
  className?: string;
}

export const WatchLivePage: React.FC<WatchLivePageProps> = ({
  data = CANONICAL_DEMO_DATA,
  onNavigate,
  className = "",
}) => {
  const testersData: TesterCardData[] = [
    {
      id: "tom",
      name: "Tom",
      label: "Expert",
      colour: "var(--tom)",
      state: "finished",
      activityText: "All tasks attempted.",
      progressText: undefined,
      frameAriaLabel: "Tom's test browser: Thread & Co. order complete page",
      frameContent: (
        <div className="flex flex-col gap-2">
          <div className="font-meta-label" style={{ color: "var(--ink-faint)" }}>
            THREAD & CO.
          </div>
          <div className="font-h3" style={{ fontSize: "16px", color: "var(--ink)" }}>
            Order #84920 Confirmed
          </div>
          <p className="font-body-small" style={{ color: "var(--ink-2)", margin: 0 }}>
            Thank you for your order. We&apos;ll send tracking details to your email.
          </p>
          <div
            style={{
              display: "inline-block",
              padding: "4px 8px",
              backgroundColor: "var(--works-tint)",
              color: "var(--works)",
              borderRadius: "4px",
              fontSize: "12px",
              fontWeight: 600,
              width: "fit-content",
            }}
          >
            ✓ Paid $28.00
          </div>
        </div>
      ),
    },
    {
      id: "maya",
      name: "Maya",
      label: "First-time user",
      colour: "var(--maya)",
      state: "doing",
      activityText: "Buy a t-shirt — step 5 of 7 · At checkout — about to pay",
      progressText: "2 steps left",
      frameAriaLabel: "Maya's test browser: Thread & Co. checkout, about to pay",
      frameContent: (
        <div className="flex flex-col gap-2">
          <div className="font-meta-label" style={{ color: "var(--ink-faint)" }}>
            THREAD & CO. · CHECKOUT
          </div>
          <div className="font-body" style={{ fontWeight: 600, color: "var(--ink)" }}>
            1 item: Classic tee (M, Navy) — $28.00
          </div>
          <div
            style={{
              padding: "8px 16px",
              border: "1px solid var(--ink)",
              fontFamily: "IBM Plex Mono, monospace",
              fontSize: "12px",
              fontWeight: 600,
              display: "inline-block",
              width: "fit-content",
              backgroundColor: "var(--card)",
            }}
          >
            Pay $28.00
          </div>
        </div>
      ),
    },
    {
      id: "priya",
      name: "Priya",
      label: "Impatient mobile user",
      colour: "var(--priya)",
      state: "needs-help",
      activityText: "Track an order — waiting for a login",
      waitingText: "Waiting 6 minutes",
      frameAriaLabel: "Priya's test browser: Thread & Co. order tracking login",
      frameContent: (
        <div className="flex flex-col gap-2">
          <div className="font-meta-label" style={{ color: "var(--ink-faint)" }}>
            THREAD & CO.
          </div>
          <div className="font-h3" style={{ fontSize: "16px", color: "var(--ink)" }}>
            Track your order
          </div>
          <p className="font-body-small" style={{ color: "var(--ink-2)", margin: 0 }}>
            Log in to see where your order is.
          </p>
          <div className="flex flex-col gap-1 mt-2">
            <div
              style={{
                height: "28px",
                border: "1px solid var(--line)",
                backgroundColor: "var(--card)",
                padding: "4px 8px",
                fontSize: "12px",
                color: "var(--ink-faint)",
              }}
            >
              Order email address
            </div>
          </div>
        </div>
      ),
    },
  ];

  return (
    <div
      className={`concept-watch-live-view min-h-screen ${className}`}
      style={{
        backgroundColor: "var(--paper)",
        color: "var(--ink)",
      }}
    >
      {/* Workspace Header 56px */}
      <header
        className="w-full flex items-center justify-between"
        style={{
          height: "56px",
          backgroundColor: "var(--card)",
          borderBottom: "1px solid var(--line)",
          paddingLeft: "32px",
          paddingRight: "32px",
        }}
      >
        <div className="flex items-center gap-8">
          <button
            type="button"
            onClick={() => onNavigate && onNavigate("Dashboard")}
            className="font-sans font-semibold text-lg cursor-pointer"
            style={{ color: "var(--ink)", background: "none", border: "none", padding: 0 }}
          >
            MarketTwin
          </button>

          <nav className="hidden sm:flex items-center gap-6 font-grid-cell">
            {["Dashboard", "Needs your help", "Your apps", "Tests", "Testers", "Settings"].map(
              (item) => {
                const isActive = item === "Tests";
                return (
                  <button
                    key={item}
                    type="button"
                    onClick={() => onNavigate && onNavigate(item)}
                    style={{
                      background: "none",
                      border: "none",
                      padding: "8px 0",
                      cursor: "pointer",
                      color: isActive ? "var(--ink)" : "var(--ink-2)",
                      fontWeight: isActive ? 600 : 400,
                      borderBottom: isActive ? "2px solid var(--ink)" : "none",
                    }}
                  >
                    {item}
                  </button>
                );
              }
            )}
          </nav>
        </div>

        <div
          style={{
            width: "32px",
            height: "32px",
            borderRadius: "50%",
            backgroundColor: "var(--ink)",
            color: "#FFFFFF",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "12px",
            fontWeight: 600,
          }}
          aria-label="Alex Morgan"
        >
          AM
        </div>
      </header>

      {/* In-test Context Row + Tabs */}
      <ContextTabs
        appContextText="THREAD & CO. · TEST · SAT 31 OCT 2026"
        activeTab="Watch live"
        onTabChange={(tab) => onNavigate && onNavigate(tab)}
      />

      {/* Main Content Container */}
      <main className="concept-workspace-container" style={{ paddingTop: "32px", paddingBottom: "64px" }}>
        {/* Header Block */}
        <div style={{ marginBottom: "32px" }}>
          <div className="flex items-center gap-3" style={{ marginBottom: "12px" }}>
            <h1 className="font-h1-workspace" style={{ color: "var(--ink)", margin: 0 }}>
              Watch live
            </h1>
            <span
              className="font-meta-label"
              style={{
                padding: "4px 10px",
                borderRadius: "999px",
                backgroundColor: "var(--notchecked-tint)",
                color: "var(--notchecked)",
                border: "1px solid var(--line)",
              }}
            >
              Sample data
            </span>
          </div>

          <div className="flex flex-col gap-2">
            <div className="font-body" style={{ color: "var(--ink)" }}>
              1 of 3 testers finished · 9 of 18 attempts done
            </div>
            <div className="font-body" style={{ fontWeight: 600, color: "var(--ink)" }}>
              9 attempts to go.
            </div>
            <div className="font-body-small" style={{ color: "var(--ink-2)" }}>
              Started {data.live.startedMinutesAgo} minutes ago
            </div>
          </div>
        </div>

        {/* Tester Cards Grid (3 cards in row on desktop, stack ≤900px) */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {testersData.map((tester) => (
            <TesterCard key={tester.id} tester={tester} />
          ))}
        </div>
      </main>
    </div>
  );
};

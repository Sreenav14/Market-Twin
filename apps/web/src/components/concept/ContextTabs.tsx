import React, { useRef } from "react";

export type InTestTab = "Test results" | "Watch live";

interface ContextTabsProps {
  appContextText?: string;
  activeTab: InTestTab;
  onTabChange: (tab: InTestTab) => void;
  className?: string;
}

export const ContextTabs: React.FC<ContextTabsProps> = ({
  appContextText = "THREAD & CO. · TEST · SAT 31 OCT 2026",
  activeTab,
  onTabChange,
  className = "",
}) => {
  const tabs: InTestTab[] = ["Test results", "Watch live"];
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    let nextIndex = index;
    if (e.key === "ArrowRight") {
      nextIndex = (index + 1) % tabs.length;
    } else if (e.key === "ArrowLeft") {
      nextIndex = (index - 1 + tabs.length) % tabs.length;
    } else if (e.key === "Home") {
      nextIndex = 0;
    } else if (e.key === "End") {
      nextIndex = tabs.length - 1;
    } else {
      return;
    }

    e.preventDefault();
    onTabChange(tabs[nextIndex]);
    tabRefs.current[nextIndex]?.focus();
  };

  return (
    <div
      className={`concept-in-test-chrome ${className}`}
      style={{
        borderBottom: "1px solid var(--line)",
        backgroundColor: "var(--card)",
      }}
    >
      {/* Context row (44px) */}
      <div
        className="flex items-center font-meta-label"
        style={{
          height: "44px",
          color: "var(--ink-2)",
          borderBottom: "1px solid var(--line)",
          paddingLeft: "32px",
          paddingRight: "32px",
        }}
      >
        {appContextText}
      </div>

      {/* Tab strip */}
      <div
        role="tablist"
        aria-label="In-test views"
        className="flex items-center gap-2"
        style={{
          paddingLeft: "32px",
          paddingRight: "32px",
          overflowX: "auto",
          flexWrap: "nowrap",
        }}
      >
        {tabs.map((tab, idx) => {
          const isSelected = activeTab === tab;
          return (
            <button
              key={tab}
              ref={(el) => {
                tabRefs.current[idx] = el;
              }}
              role="tab"
              aria-selected={isSelected}
              tabIndex={isSelected ? 0 : -1}
              onClick={() => onTabChange(tab)}
              onKeyDown={(e) => handleKeyDown(e, idx)}
              className="font-button-label flex items-center justify-center transition-colors"
              style={{
                minHeight: "44px",
                padding: "12px 16px",
                color: isSelected ? "var(--ink)" : "var(--ink-2)",
                backgroundColor: "transparent",
                border: "none",
                borderRadius: 0,
                cursor: "pointer",
                whiteSpace: "nowrap",
                flexShrink: 0,
                boxShadow: isSelected ? "inset 0 -2px 0 var(--ink)" : "none",
              }}
            >
              {tab}
            </button>
          );
        })}
      </div>
    </div>
  );
};

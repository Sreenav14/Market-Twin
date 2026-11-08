import React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";

export type InTestTab = "Test results" | "Watch live";

interface ContextTabsProps {
  appContextText?: string;
  activeTab: InTestTab;
  onTabChange: (tab: InTestTab) => void;
  className?: string;
}

/* Migrated (Phase 2c) onto the ONE tabs recipe: Radix Tabs
   (APG tablist/tab, roving tabindex, automatic activation) with
   the shared .mt-tab treatment from overlays.css \u00a71a. The panels
   are the two concept pages' main regions, labelled by these tabs. */
export const ContextTabs: React.FC<ContextTabsProps> = ({
  appContextText = "THREAD & CO. \u00b7 TEST \u00b7 SAT 31 OCT 2026",
  activeTab,
  onTabChange,
  className = "",
}) => {
  const tabs: InTestTab[] = ["Test results", "Watch live"];
  return (
    <div
      className={`concept-in-test-chrome ${className}`}
      style={{
        borderBottom: "1px solid var(--line)",
        backgroundColor: "var(--card)",
      }}
    >
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
      <TabsPrimitive.Root
        value={activeTab}
        onValueChange={(value) => onTabChange(value as InTestTab)}
      >
        <TabsPrimitive.List
          className="mt-tabs-list"
          aria-label="In-test views"
          style={{ paddingLeft: "32px", paddingRight: "32px", borderBottom: "none" }}
        >
          {tabs.map((tab) => (
            <TabsPrimitive.Trigger key={tab} value={tab} className="mt-tab">
              {tab}
            </TabsPrimitive.Trigger>
          ))}
        </TabsPrimitive.List>
      </TabsPrimitive.Root>
    </div>
  );
};

import * as TabsPrimitive from "@radix-ui/react-tabs";
import type { ReactNode } from "react";

/* ONE tabs recipe (Phase 2c, Spec 2 §7): APG Tabs via Radix —
   tablist/tab/tabpanel, roving tabindex, Arrow/Home/End,
   automatic activation. Navigation strips are NOT tabs: they use
   .tab-strip/.tab-link with NavLink + aria-current (overlays.css). */

export function Tabs({
  label,
  value,
  onValueChange,
  tabs,
  children,
  className = "",
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  tabs: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <TabsPrimitive.Root value={value} onValueChange={onValueChange} className={className}>
      <TabsPrimitive.List className="mt-tabs-list" aria-label={label}>
        {tabs}
      </TabsPrimitive.List>
      {children}
    </TabsPrimitive.Root>
  );
}

export function Tab({
  value,
  children,
  disabled = false,
}: {
  value: string;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <TabsPrimitive.Trigger value={value} disabled={disabled} className="mt-tab">
      {children}
    </TabsPrimitive.Trigger>
  );
}

export function TabPanel({
  value,
  children,
  flush = false,
}: {
  value: string;
  children: ReactNode;
  flush?: boolean;
}) {
  return (
    <TabsPrimitive.Content
      value={value}
      className={flush ? "mt-tabpanel mt-tabpanel--flush" : "mt-tabpanel"}
    >
      {children}
    </TabsPrimitive.Content>
  );
}

/* Compound form for call sites that render panels conditionally
   outside the root (legacy shapes): a standalone list + triggers
   wired to an external panel, keeping the same APG contract. */
export const TabsList = TabsPrimitive.List;
export const TabsTrigger = TabsPrimitive.Trigger;
export const TabsRoot = TabsPrimitive.Root;
export const TabsContent = TabsPrimitive.Content;

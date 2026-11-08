import type { NavigateFunction } from "react-router-dom";
import type { IconName } from "../components/ui/Icon";

/* ONE registry for destinations (Phase 2c, Spec 2 §2.4 decisive
   ruling): the visible shell navigation and the command palette
   derive from this single list, and every palette selection runs
   through the single runCommand() path below. A second
   hand-maintained destination list will drift — there is none. */

export interface NavCommand {
  id: string;
  title: string;
  description: string;
  href: string;
  icon: IconName;
  keywords: string;
  /** Shell-nav active state is route-prefix based for these. */
  activePrefixes?: string[];
}

export const NAV_COMMANDS: NavCommand[] = [
  { id: "home", title: "Home", description: "Applications and test activity", href: "/dashboard", icon: "home", keywords: "dashboard briefing desk" },
  { id: "apps", title: "Your apps", description: "Choose a product or start a test", href: "/applications", icon: "apps", keywords: "applications products", activePrefixes: ["/applications", "/targets"] },
  { id: "tests", title: "Tests", description: "Find a test and inspect its results", href: "/runs", icon: "runs", keywords: "runs results", activePrefixes: ["/runs"] },
  { id: "knowledge", title: "Knowledge", description: "Review and approve knowledge for tests", href: "/knowledge/review", icon: "knowledge", keywords: "review approve sources", activePrefixes: ["/knowledge"] },
  { id: "add-knowledge", title: "Add knowledge", description: "Add knowledge from source files or links", href: "/ingestion", icon: "ingestion", keywords: "ingest upload link source" },
  { id: "testers", title: "Testers", description: "Inspect tester instructions and prepare another test", href: "/agents", icon: "user", keywords: "agents personas instructions" },
  { id: "settings", title: "Settings", description: "Your account and workspace", href: "/settings", icon: "settings", keywords: "profile account workspace billing" },
];

export function filterNavCommands(query: string): NavCommand[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return NAV_COMMANDS;
  return NAV_COMMANDS.filter((command) =>
    `${command.title} ${command.description} ${command.keywords}`.toLowerCase().includes(needle),
  );
}

/** The single command path: execute, then the caller closes. */
export function runCommand(navigate: NavigateFunction, command: NavCommand): void {
  navigate(command.href);
}

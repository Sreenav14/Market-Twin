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
  { id: "apps", title: "Apps", description: "Choose an application or manage its personas", href: "/applications", icon: "apps", keywords: "your apps products testers instructions", activePrefixes: ["/applications", "/targets"] },
  { id: "knowledge", title: "Knowledge", description: "Build application knowledge and review learned skills", href: "/knowledge", icon: "knowledge", keywords: "ingestion learn map skills", activePrefixes: ["/knowledge"] },
  { id: "tests", title: "Tests", description: "Start a test or inspect its results", href: "/runs", icon: "runs", keywords: "runs results visual audit slop look quality", activePrefixes: ["/runs"] },
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

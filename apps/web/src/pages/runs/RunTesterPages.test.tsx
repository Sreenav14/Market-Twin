import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { RunContext } from "../../layouts/RunLayout";
import { api, type JourneyExecution } from "../../lib/api";
import { RunMissionsPage } from "./RunMissionsPage";
import { RunPerspectivesPage } from "./RunPerspectivesPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function journey(overrides: Partial<JourneyExecution>): JourneyExecution {
  return {
    id: "journey", ordinal: 1, persona_name: "New visitor", persona_perspective: "Arrives from search.",
    mission_title: "Create account", mission_objective: "Sign up for a trial.", step_count: 2, artifact_count: 1,
    evidence_available: true, summary: null, success_criteria: ["Account form is visible"], execution_id: "execution", attempt_number: 1,
    execution_status: "completed", outcome: "passed", started_at: null, completed_at: null, error_message: null, result: null,
    ...overrides,
  };
}

function mount(page: "perspectives" | "missions", executionMode = "legacy_persona") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const context: RunContext = {
    run: { id: "run", workspace_id: "workspace", application_id: "application", target_id: "target", created_by_user_id: "operator", target_snapshot: {}, status: "completed", configuration_snapshot: { study_brief: "Check sign-up", execution_mode: executionMode } },
    user: { id: "operator", email: "synthetic@example.test", normalized_email: "synthetic@example.test", display_name: null },
    workspace: { id: "workspace", name: "Synthetic workspace", status: "active", role: "owner" },
    results: { status: "waiting", data: null, error: null }, refresh: () => {},
  };
  function Layout() { return <Outlet context={context} />; }
  const Page = page === "perspectives" ? RunPerspectivesPage : RunMissionsPage;
  render(<QueryClientProvider client={client}><MemoryRouter><Routes><Route element={<Layout />}><Route path="*" element={<Page />} /></Route></Routes></MemoryRouter></QueryClientProvider>);
}

const journeys = [
  journey({ id: "j1", persona_name: "New visitor", mission_title: "Create account", outcome: "passed" }),
  journey({ id: "j2", persona_name: "New visitor", mission_title: "Find pricing", execution_status: "failed", outcome: "inconclusive" }),
  journey({ id: "j3", persona_name: "Returning user", mission_title: "Create account", outcome: null, execution_status: null }),
  journey({ id: "discovery", ordinal: 10000, runtime_name: "browser_discovery_v1", persona_name: "Browser discovery", mission_title: "Discovery" }),
];

it("groups saved journeys under each simulated tester and excludes discovery", async () => {
  vi.spyOn(api, "getRunJourneys").mockResolvedValue(journeys);
  mount("perspectives");
  expect(await screen.findByRole("heading", { name: "New visitor" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Returning user" })).toBeInTheDocument();
  expect(screen.getByText("2 planned journeys")).toBeInTheDocument();
  expect(screen.getByText("1 completed · 1 failed")).toBeInTheDocument();
  expect(screen.getByText("1 passed · 1 inconclusive")).toBeInTheDocument();
  expect(screen.getAllByText("1 not recorded")).toHaveLength(2);
  expect(screen.queryByText("Browser discovery")).not.toBeInTheDocument();
  expect(screen.queryByText(/Exactly three/)).not.toBeInTheDocument();
});

it("lists testing goals with their saved success criteria and no placeholder claims", async () => {
  vi.spyOn(api, "getRunJourneys").mockResolvedValue(journeys);
  mount("missions");
  expect(await screen.findByRole("heading", { name: "Create account" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Find pricing" })).toBeInTheDocument();
  expect(screen.getAllByText("Account form is visible")).toHaveLength(2);
  expect(screen.getByText("New visitor, Returning user")).toBeInTheDocument();
  expect(screen.queryByText(/One to four bounded missions/)).not.toBeInTheDocument();
});

it("explains that Feature Cases have no simulated testers", async () => {
  const spy = vi.spyOn(api, "getRunJourneys").mockResolvedValue(journeys);
  mount("perspectives", "deep_feature_v1");
  expect(await screen.findByText("Feature Cases do not use simulated testers")).toBeInTheDocument();
  expect(spy).toHaveBeenCalled();
});

it("shows an honest empty state when no journeys are planned", async () => {
  vi.spyOn(api, "getRunJourneys").mockResolvedValue([]);
  mount("missions");
  expect(await screen.findByText("No testing goals planned yet")).toBeInTheDocument();
});

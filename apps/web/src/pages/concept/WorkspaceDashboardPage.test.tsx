import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { AppShellContext } from "../../layouts/AppShell";
import { api, type HumanAction, type JourneyExecution, type RunResults, type TestRun } from "../../lib/api";
import { WorkspaceDashboardPage } from "./WorkspaceDashboardPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function runFixture(id: string, status: string, created_at: string, test_name: string): TestRun {
  return {
    id, status, created_at, workspace_id: "workspace", application_id: "app", target_id: "target",
    created_by_user_id: "user", target_snapshot: {}, configuration_snapshot: { test_name },
  } as TestRun;
}

interface DetailMocks {
  humanActions?: HumanAction[];
  journeys?: JourneyExecution[];
  results?: RunResults;
}

async function mount(runs: TestRun[], detail: DetailMocks = {}) {
  vi.spyOn(api, "listApplications").mockResolvedValue([{ id: "app", workspace_id: "workspace", created_by_user_id: "user", name: "Fixture app", description: null, status: "active" }] as Awaited<ReturnType<typeof api.listApplications>>);
  vi.spyOn(api, "listRuns").mockResolvedValue(runs);
  // Home fetches detail for its featured runs only (HR-2..HR-4); default to
  // empty detail so the list-level behaviour stays what these tests assert.
  vi.spyOn(api, "listHumanActions").mockResolvedValue(detail.humanActions ?? []);
  vi.spyOn(api, "getRunJourneys").mockResolvedValue(detail.journeys ?? []);
  vi.spyOn(api, "getRunResults").mockResolvedValue(detail.results ?? {
    test_run_id: "done", report: { id: "report", version: 1, status: "completed", executive_summary: null, payload: {}, generated_at: null }, findings: [],
  } as RunResults);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/dashboard"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/dashboard" element={<WorkspaceDashboardPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("heading", { name: "Home", level: 1 });
  // The heading now renders during loading too (SI-8, so the page does not
  // jump when data lands), so mounting must wait for the loaded sections.
  await screen.findByRole("region", { name: "Happening now" });
}

it("links the needs-you row to the oldest awaiting_human run", async () => {
  await mount([
    runFixture("newer", "awaiting_human", "2026-11-02T10:00:00Z", "Newer parked test"),
    runFixture("oldest", "awaiting_human", "2026-11-01T10:00:00Z", "Oldest parked test"),
    runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test"),
  ]);
  const section = screen.getByRole("region", { name: "Needs your help" });
  expect(within(section).getByText(/Needs you — the tester is paused/)).toBeInTheDocument();
  expect(within(section).getAllByRole("link", { name: /Help this tester/ })[0]).toHaveAttribute("href", "/runs/oldest/human-action");
});

it("shows no needs-you row when no run is awaiting_human", async () => {
  await mount([runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test")]);
  expect(screen.queryByText(/Needs you — the tester is paused/)).not.toBeInTheDocument();
});

it("briefs the snapshot and shows the agent's actual request on the featured card", async () => {
  await mount([
    runFixture("parked", "awaiting_human", "2026-11-01T10:00:00Z", "Checkout test"),
    runFixture("live", "queued", "2026-11-03T10:00:00Z", "Signup test"),
  ], {
    humanActions: [{
      id: "ha-1", test_run_id: "parked", execution_id: "exec", browser_session_id: "browser",
      request_type: "login", journey_title: "Checkout test", requesting_agent: "Lead Testing Agent",
      instructions: "Please log in so the tester can continue.", status: "pending",
      created_at: "2026-11-01T10:05:00Z", expires_at: null, control_generation: 1,
      lease_id: null, lease_expires_at: null,
    } as HumanAction],
  });
  // The snapshot clause names the waiting test; the featured card carries
  // the pending human-action's own words, not a paraphrase.
  expect(await screen.findByText(/is waiting for you/)).toBeInTheDocument();
  const section = screen.getByRole("region", { name: "Needs your help" });
  expect(await within(section).findByText(/Please log in so the tester can continue\./)).toBeInTheDocument();
  expect(within(section).getByText(/Lead Testing Agent/)).toBeInTheDocument();
});

it("leads Recent tests with the finished run's real outcome and report summary", async () => {
  await mount([
    runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test"),
    runFixture("failed", "failed", "2026-11-02T10:00:00Z", "Failed test"),
  ], {
    results: {
      test_run_id: "done",
      report: {
        id: "report", version: 1, status: "completed",
        executive_summary: "One journey did not meet its success criteria.",
        payload: { journeys: { total: 2, outcome_counts: { passed: 1, failed: 1 } } },
        generated_at: "2026-11-03T11:00:00Z",
      },
      findings: [],
    } as unknown as RunResults,
  });
  const section = screen.getByRole("region", { name: "Recent tests" });
  expect(await within(section).findByText("1 of 2 journeys worked · 0 findings")).toBeInTheDocument();
  expect(within(section).getByText("One journey did not meet its success criteria.")).toBeInTheDocument();
  // The featured run is not repeated as a plain row underneath itself.
  expect(within(section).getAllByText(/Finished test/)).toHaveLength(1);
});

it("filters the recent list by finished status", async () => {
  await mount([
    runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test"),
    runFixture("failed", "failed", "2026-11-02T10:00:00Z", "Failed test"),
    runFixture("stopped", "cancelled", "2026-11-01T10:00:00Z", "Stopped test"),
  ]);
  const section = screen.getByRole("region", { name: "Recent tests" });
  expect(within(section).getByText(/Failed test/)).toBeInTheDocument();
  expect(within(section).getByText(/Stopped test/)).toBeInTheDocument();
  fireEvent.click(within(section).getByRole("button", { name: /Failed · 1/ }));
  expect(within(section).getByText(/Failed test/)).toBeInTheDocument();
  expect(within(section).queryByText(/Stopped test/)).not.toBeInTheDocument();
  fireEvent.click(within(section).getByRole("button", { name: /All · 3/ }));
  expect(within(section).getByText(/Stopped test/)).toBeInTheDocument();
});

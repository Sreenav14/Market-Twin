import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { AppShellContext } from "../../layouts/AppShell";
import {
  api,
  type HumanAction,
  type IngestionSummary,
  type JourneyExecution,
  type LatestRunSummary,
  type RunResults,
  type TestRun,
} from "../../lib/api";
import { testDestination, WorkspaceDashboardPage } from "./WorkspaceDashboardPage";

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
  ingestion?: IngestionSummary[];
  applications?: { id: string; name: string; latest_run_summary?: LatestRunSummary | null }[];
}

async function mount(runs: TestRun[], detail: DetailMocks = {}) {
  const apps = detail.applications ?? [{ id: "app", name: "Fixture app" }];
  vi.spyOn(api, "listApplications").mockResolvedValue(apps.map((app) => ({
    id: app.id, workspace_id: "workspace", created_by_user_id: "user",
    name: app.name, description: null, status: "active",
    latest_run_summary: app.latest_run_summary ?? null,
  })) as Awaited<ReturnType<typeof api.listApplications>>);
  vi.spyOn(api, "listRuns").mockResolvedValue(runs);
  vi.spyOn(api, "listHumanActions").mockResolvedValue(detail.humanActions ?? []);
  vi.spyOn(api, "getRunJourneys").mockResolvedValue(detail.journeys ?? []);
  vi.spyOn(api, "listIngestion").mockResolvedValue(detail.ingestion ?? []);
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
  await screen.findByRole("region", { name: /YOUR APPS|EXAMPLE/ });
}

const contractResults: RunResults = {
  test_run_id: "done",
  report: {
    id: "report", version: 1, status: "completed",
    executive_summary: "The pay button did nothing when Maya tapped it, so the run is not ready. Everything else in the approved journeys behaved as the checks expected, and the full detail is in the report.",
    payload: {
      market_verdict: { verdict: "not_ready", confirmed_defects: 1, journeys_executed: 2, journeys_approved: 2 },
      journeys: [
        { journey_key: "buy", title: "Buy a t-shirt", feature_key: "checkout", checks: [] },
        { journey_key: "search", title: "Search for a t-shirt", feature_key: "search", checks: [] },
      ],
      what_works: ["search"],
      confirmed: [{ check: "Pay button submits the order", journey_key: "buy", finding_id: "f1", screenshot_artifact_ids: [] }],
      cases: [
        { journey_key: "buy", verdict: "failed", persona_index: 0 },
        { journey_key: "search", verdict: "passed", persona_index: 0 },
      ],
      coverage: { tested_features: 2, discovered_features: 2, approved: 2 },
      experience: {
        personas: [{
          name: "Maya", persona_name: "Maya", status: "completed",
          facts: { journeys_completed: 1, journeys_attempted: 2, total_steps: 9, failed_actions: 1, timeouts: 0, checks_passed: 3, checks_failed: 1, stuck_points: [] },
          scores: { dimensions: { ease: { justification: "The pay button just sat there [failed_actions=1]. I did not know if I had been charged." } } },
        }],
      },
    },
    generated_at: "2026-11-03T11:00:00Z",
  },
  findings: [],
} as unknown as RunResults;

it("state E: the masthead leads with the locked verdict word, outcome links and reproduced evidence", async () => {
  await mount([runFixture("done", "completed", "2026-11-03T10:00:00Z", "Checkout test")], { results: contractResults });
  expect(await screen.findByRole("heading", { name: "Not ready yet", level: 2 })).toBeInTheDocument();
  expect(screen.getByText(/LATEST RESULT — FIXTURE APP/)).toBeInTheDocument();
  // Outcome segments deep-link into the filtered result.
  expect(screen.getByRole("link", { name: /1 Broken/ })).toHaveAttribute("href", "/runs/done/results?outcome=broken");
  expect(screen.getByRole("link", { name: /1 Worked/ })).toHaveAttribute("href", "/runs/done/results?outcome=worked");
  // Basis is the report's own summary, truncated, with the full-result link.
  expect(screen.getByText(/The pay button did nothing when Maya tapped it/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Read the full result/ })).toHaveAttribute("href", "/runs/done/results");
  // Evidence: the confirmed problem, titled as a failure, reproduced.
  expect(screen.getByText("Failed: Pay button submits the order")).toBeInTheDocument();
  expect(screen.getByText(/Reproduced in a fresh browser\./)).toBeInTheDocument();
  // Voices: the tester's verbatim words, metric tokens stripped, no scores.
  expect(screen.getByText(/The pay button just sat there\. I did not know if I had been charged\./)).toBeInTheDocument();
  expect(screen.getByText(/Maya, simulated tester/)).toBeInTheDocument();
  expect(screen.getByText("MarketTwin only counts defects reproduced in a fresh browser.")).toBeInTheDocument();
});

it("the tray quotes the Lead Agent's request verbatim and links to help", async () => {
  await mount([
    runFixture("parked", "awaiting_human", "2026-11-01T10:00:00Z", "Checkout test"),
    runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test"),
  ], {
    humanActions: [{
      id: "ha-1", test_run_id: "parked", execution_id: "exec", browser_session_id: "browser",
      request_type: "login", journey_title: "Buy a t-shirt", requesting_agent: "Lead Testing Agent",
      requested_by_step_id: 4,
      instructions: "Please log in so the tester can continue.", status: "pending",
      created_at: "2026-11-01T10:05:00Z", expires_at: null, control_generation: 1,
      lease_id: null, lease_expires_at: null,
    } as HumanAction],
  });
  const tray = screen.getByRole("region", { name: /NEEDS YOU — 1/ });
  expect(await within(tray).findByText("Please log in so the tester can continue.")).toBeInTheDocument();
  expect(within(tray).getByText(/THE LEAD AGENT · ON BUY A T-SHIRT · FIXTURE APP/)).toBeInTheDocument();
  expect(within(tray).getByText(/Tester paused at step 4/)).toBeInTheDocument();
  expect(within(tray).getByRole("link", { name: /Help now/ })).toHaveAttribute("href", "/runs/parked/human-action");
});

it("a knowledge entry awaiting review joins the tray without an inline approve", async () => {
  await mount([runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test")], {
    ingestion: [{
      id: "k1", workspace_id: "workspace", name: "Pricing guide", source_name: "pricing.pdf",
      status: "draft", roles: [], created_at: "2026-11-02T10:00:00Z", approved_at: null,
      knowledge_count: 3, artifact_count: 0, skill_count: 1, issue_count: 0,
      processing_status: "ready", processing_stage: "review",
    } as IngestionSummary],
  });
  const tray = screen.getByRole("region", { name: /NEEDS YOU — 1/ });
  expect(within(tray).getByRole("link", { name: /Review knowledge/ })).toHaveAttribute("href", "/knowledge/review/k1");
  expect(within(tray).queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
});

it("an empty tray is exactly one calm line", async () => {
  await mount([runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test")]);
  expect(screen.getByText("Nothing needs you.")).toBeInTheDocument();
});

it("state G: a failed latest run is not a verdict on the app", async () => {
  await mount([
    runFixture("failed", "failed", "2026-11-04T10:00:00Z", "Crashed test"),
    runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test"),
  ], { results: contractResults });
  expect(await screen.findByRole("heading", { name: "Latest run failed", level: 2 })).toBeInTheDocument();
  expect(screen.getByText(/Previous result — Fixture app:/)).toBeInTheDocument();
  expect(screen.getByText("Not ready yet")).toBeInTheDocument();
});

it("state B: apps but no runs invites the first test", async () => {
  await mount([]);
  expect(await screen.findByText("Ready when you are.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Start first test" })).toHaveAttribute("href", "/applications/app/runs/new");
});

it("state A: no apps shows a labelled example briefing, never fake live data", async () => {
  await mount([], { applications: [] });
  expect(await screen.findByText("Your briefing desk.")).toBeInTheDocument();
  expect(screen.getByText(/EXAMPLE — HOW YOUR BRIEFING WILL LOOK/)).toBeInTheDocument();
  expect(screen.getByText("Pay button does nothing")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Add an app" })).toHaveAttribute("href", "/applications/new");
});

it("state C: a first run in progress promotes the live strip", async () => {
  await mount([runFixture("live", "running", "2026-11-03T10:00:00Z", "First test")], {
    journeys: [{
      id: "j1", ordinal: 1, persona_name: "Tom", persona_perspective: "Expert", mission_title: "Buy",
      mission_objective: "Buy", step_count: 6, artifact_count: 0, evidence_available: true, summary: null,
      success_criteria: [], execution_id: "e1", attempt_number: 1, execution_status: "running",
      outcome: null, started_at: null, completed_at: null, error_message: null, result: null,
    } as JourneyExecution],
  });
  expect(await screen.findByText("YOUR TEST IS UNDER WAY")).toBeInTheDocument();
  expect(screen.getByText(/0 of 1 journey finished · 6 steps recorded so far/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Watch live/ })).toHaveAttribute("href", "/runs/live/watch");
});

it("filters the recent list by finished status and never repeats the masthead run", async () => {
  await mount([
    runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test"),
    runFixture("failed", "failed", "2026-11-02T10:00:00Z", "Failed test"),
    runFixture("stopped", "cancelled", "2026-11-01T10:00:00Z", "Stopped test"),
  ]);
  const section = screen.getByRole("region", { name: "RECENT TESTS" });
  expect(within(section).getByText(/Failed test/)).toBeInTheDocument();
  expect(within(section).getByText(/Stopped test/)).toBeInTheDocument();
  expect(within(section).queryByText(/Finished test/)).not.toBeInTheDocument();
  fireEvent.click(within(section).getByRole("button", { name: /Failed · 1/ }));
  // Motion (home-motion §4e): a filtered-out row fades over the 150ms
  // exit duration before it is removed — it does not vanish instantly.
  expect(within(section).getByText(/Stopped test/).closest("article")).toHaveClass("desk-row-leaving");
  await waitFor(() => expect(within(section).queryByText(/Stopped test/)).not.toBeInTheDocument());
  fireEvent.click(within(section).getByRole("button", { name: /All · 3/ }));
  expect(within(section).getByText(/Stopped test/)).toBeInTheDocument();
});

it("the apps rail shows the last verdict per app, and nothing extra without one", async () => {
  await mount([], {
    applications: [
      {
        id: "thread", name: "Thread & Co.",
        latest_run_summary: {
          latest_run_id: "run-9", latest_run_status: "completed",
          verdict: "not_ready", finished_at: "2026-11-05T15:30:00Z",
        },
      },
      { id: "memory", name: "SuperMemory", latest_run_summary: null },
    ],
  });
  const rail = screen.getByRole("region", { name: "YOUR APPS" });
  const threadRow = within(rail).getByRole("link", { name: "Thread & Co." }).closest("article") as HTMLElement;
  expect(within(threadRow).getByText("Not ready yet")).toBeInTheDocument();
  expect(within(threadRow).getByText(/Finished .*2026/)).toBeInTheDocument();
  const memoryRow = within(rail).getByRole("link", { name: "SuperMemory" }).closest("article") as HTMLElement;
  expect(within(memoryRow).queryByText(/Finished/)).not.toBeInTheDocument();
  expect(within(memoryRow).queryByText("Not ready yet")).not.toBeInTheDocument();
  expect(within(memoryRow).getByText("Open →")).toBeInTheDocument();
});

it("the apps rail prints the locked word for a ready verdict", async () => {
  await mount([], {
    applications: [{
      id: "klaviyo", name: "Klaviyo",
      latest_run_summary: {
        latest_run_id: "run-3", latest_run_status: "completed",
        verdict: "ready_with_issues", finished_at: "2026-11-04T09:15:00Z",
      },
    }],
  });
  const rail = screen.getByRole("region", { name: "YOUR APPS" });
  expect(within(rail).getByText("Ready with issues")).toBeInTheDocument();
  expect(within(rail).getByText(/Finished .*2026/)).toBeInTheDocument();
});

it("an app whose last report has no verdict shows its finish time without a verdict word", async () => {
  await mount([], {
    applications: [{
      id: "legacy", name: "Legacy app",
      latest_run_summary: {
        latest_run_id: "run-1", latest_run_status: "completed",
        verdict: null, finished_at: "2026-11-02T08:00:00Z",
      },
    }],
  });
  const rail = screen.getByRole("region", { name: "YOUR APPS" });
  expect(within(rail).getByText(/Finished .*2026/)).toBeInTheDocument();
  expect(within(rail).queryByText(/Ready|Can't tell/)).not.toBeInTheDocument();
});

it("testDestination never offers a live watch for a run that is not running", () => {
  expect(testDestination(runFixture("q", "queued", "2026-11-03T10:00:00Z", "Queued"))).toEqual({ to: "/runs/q/overview", label: "See test details" });
  expect(testDestination(runFixture("p", "planning", "2026-11-03T10:00:00Z", "Planning"))).toEqual({ to: "/runs/p/overview", label: "See test details" });
  expect(testDestination(runFixture("r", "running", "2026-11-03T10:00:00Z", "Running"))).toEqual({ to: "/runs/r/watch", label: "Watch live" });
});

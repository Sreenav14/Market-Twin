import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { AppShellContext } from "../../layouts/AppShell";
import {
  api,
  type HumanAction,
  type JourneyExecution,
  type RunResults,
  type TestRun,
} from "../../lib/api";
import { WorkspaceDashboardPage } from "./WorkspaceDashboardPage";

/* The honest-motion invariants (home-motion research §5): motion is
   tested as logic, never as screenshot diffs. An identical poll must
   change nothing; a changed poll shows final values at t=0 (lengths
   transition underneath via transform); the tray's one attention
   event fires once per request id and never on mount; reduced motion
   renders the same end states statically. */

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete (window as { matchMedia?: unknown }).matchMedia;
});

function runFixture(id: string, status: string, created_at: string, test_name: string): TestRun {
  return {
    id, status, created_at, workspace_id: "workspace", application_id: "app", target_id: "target",
    created_by_user_id: "user", target_snapshot: {}, configuration_snapshot: { test_name },
  } as TestRun;
}

function humanAction(id: string, instructions: string, step: number): HumanAction {
  return {
    id, test_run_id: "parked", execution_id: "exec", browser_session_id: "browser",
    request_type: "login", journey_title: "Buy a t-shirt", requesting_agent: "Lead Testing Agent",
    requested_by_step_id: step, instructions, status: "pending",
    created_at: "2026-11-01T10:05:00Z", expires_at: null, control_generation: 1,
    lease_id: null, lease_expires_at: null,
  } as HumanAction;
}

function journey(id: string, persona: string, step_count: number): JourneyExecution {
  return {
    id, ordinal: 1, persona_name: persona, persona_perspective: "Expert", mission_title: "Buy",
    mission_objective: "Buy", step_count, artifact_count: 0, evidence_available: true, summary: null,
    success_criteria: [], execution_id: "e1", attempt_number: 1, execution_status: "running",
    outcome: null, started_at: null, completed_at: null, error_message: null, result: null,
  } as JourneyExecution;
}

function resultsWith(verdict: string, works: string[], confirmed: unknown[]): RunResults {
  return {
    test_run_id: "done",
    report: {
      id: "report", version: 1, status: "completed", executive_summary: null,
      payload: {
        market_verdict: { verdict, confirmed_defects: confirmed.length, journeys_executed: 2, journeys_approved: 2 },
        journeys: [
          { journey_key: "buy", title: "Buy a t-shirt", feature_key: "checkout", checks: [] },
          { journey_key: "search", title: "Search for a t-shirt", feature_key: "search", checks: [] },
        ],
        what_works: works,
        confirmed,
        cases: [
          { journey_key: "buy", verdict: works.includes("buy") ? "passed" : "failed", persona_index: 0 },
          { journey_key: "search", verdict: works.includes("search") ? "passed" : "failed", persona_index: 0 },
        ],
        coverage: { tested_features: 2, discovered_features: 2, approved: 2 },
        experience: { personas: [] },
      },
      generated_at: "2026-11-03T11:00:00Z",
    },
    findings: [],
  } as unknown as RunResults;
}

const notReadyResults = resultsWith("not_ready", ["search"], [
  { check: "Pay button submits the order", journey_key: "buy", finding_id: "f1", screenshot_artifact_ids: [] },
]);
const readyResults = resultsWith("ready", ["buy", "search"], []);

interface Sources {
  runs: TestRun[];
  humanActions: HumanAction[];
  journeys: JourneyExecution[];
  results: RunResults;
}

async function mount(sources: Sources, options: { delayApps?: boolean } = {}) {
  vi.spyOn(api, "listApplications").mockImplementation(async () => {
    if (options.delayApps) await new Promise((resolve) => setTimeout(resolve, 60));
    return [{
      id: "app", workspace_id: "workspace", created_by_user_id: "user",
      name: "Fixture app", description: null, status: "active", latest_run_summary: null,
    }] as Awaited<ReturnType<typeof api.listApplications>>;
  });
  vi.spyOn(api, "listRuns").mockImplementation(async () => sources.runs);
  vi.spyOn(api, "listHumanActions").mockImplementation(async () => sources.humanActions);
  vi.spyOn(api, "getRunJourneys").mockImplementation(async () => sources.journeys);
  vi.spyOn(api, "listIngestion").mockResolvedValue([]);
  vi.spyOn(api, "getRunResults").mockImplementation(async () => sources.results);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/dashboard"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/dashboard" element={<WorkspaceDashboardPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("heading", { name: "Home", level: 1 });
  await screen.findByRole("region", { name: /YOUR APPS/ });
  return client;
}

/** One poll cycle: every active query refetches from the sources. */
async function poll(client: QueryClient) {
  await act(async () => {
    await client.invalidateQueries();
  });
}

function trayCard(instructions: string): HTMLElement {
  const tray = screen.getByRole("region", { name: /NEEDS YOU/ });
  const quote = within(tray).getByText(instructions);
  return quote.closest("article") as HTMLElement;
}

it("(a) an identical poll changes nothing: no arrival classes, no new transforms", async () => {
  const sources: Sources = {
    runs: [
      runFixture("parked", "awaiting_human", "2026-11-01T10:00:00Z", "Checkout test"),
      runFixture("live", "running", "2026-11-03T10:00:00Z", "Live test"),
    ],
    humanActions: [humanAction("ha-1", "Please log in so the tester can continue.", 4)],
    journeys: [journey("j1", "Tom", 3), journey("j2", "Maya", 6)],
    results: notReadyResults,
  };
  const client = await mount(sources);
  const card = trayCard("Please log in so the tester can continue.");
  expect(card.className).not.toContain("desk-card-new");
  const fill = document.querySelector(".desk-step-fill") as HTMLElement;
  expect(fill.style.transform).toBe("scaleX(0.5)");

  await poll(client);

  expect(trayCard("Please log in so the tester can continue.").className).not.toContain("desk-card-new");
  expect(document.querySelector("[data-desk-enter]")).toBeNull();
  expect((document.querySelector(".desk-step-fill") as HTMLElement).style.transform).toBe("scaleX(0.5)");
});

it("(b) a changed poll shows final values at t=0; only the length transitions", async () => {
  const sources: Sources = {
    runs: [
      runFixture("live", "running", "2026-11-03T10:00:00Z", "Live test"),
      runFixture("done", "completed", "2026-11-02T10:00:00Z", "Finished test"),
    ],
    humanActions: [],
    journeys: [journey("j1", "Tom", 3), journey("j2", "Maya", 6)],
    results: notReadyResults,
  };
  const client = await mount(sources);
  // Masthead outcome bar starts at 1 worked / 1 broken.
  expect(await screen.findByRole("heading", { name: "Not ready yet", level: 2 })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /1 Worked/ })).toBeInTheDocument();

  sources.journeys = [journey("j1", "Tom", 6), journey("j2", "Maya", 6)];
  sources.results = readyResults;
  await poll(client);

  // Counts are final immediately — no counting through intermediates.
  expect(await screen.findByText(/12 steps recorded so far/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /2 Worked/ })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Broken/ })).not.toBeInTheDocument();
  // The step fill renders its final fraction; the outcome fill engaged
  // its transform transition and already targets the true length.
  expect((document.querySelector(".desk-step-fill") as HTMLElement).style.transform).toBe("scaleX(1)");
  const outcomeFill = document.querySelector(".desk-outcome-fill") as HTMLElement;
  expect(outcomeFill.style.transform).toBe("scaleX(1)");
  expect(outcomeFill.style.transition).toContain("transform");
});

it("(c) the tray's attention event fires once per new request, never on mount", async () => {
  const sources: Sources = {
    runs: [runFixture("parked", "awaiting_human", "2026-11-01T10:00:00Z", "Checkout test")],
    humanActions: [humanAction("ha-1", "Please log in so the tester can continue.", 4)],
    journeys: [],
    results: notReadyResults,
  };
  const client = await mount(sources);
  // Present since mount: seeded, no event.
  expect(trayCard("Please log in so the tester can continue.").className).not.toContain("desk-card-new");
  const cards = document.querySelector(".desk-tray-cards") as HTMLElement;
  expect(cards).toHaveAttribute("aria-live", "polite");

  sources.humanActions = [
    humanAction("ha-1", "Please log in so the tester can continue.", 4),
    humanAction("ha-2", "Please confirm the test card details.", 2),
  ];
  await poll(client);

  const arrived = await waitFor(() => {
    const element = trayCard("Please confirm the test card details.");
    expect(element.className).toContain("desk-card-new");
    return element;
  });
  expect(arrived.className).toContain("desk-enter");
  expect(trayCard("Please log in so the tester can continue.").className).not.toContain("desk-card-new");

  // A second identical poll does not re-fire; the static edge remains
  // after the one-shot enter classes are dropped.
  await poll(client);
  await waitFor(
    () => expect(trayCard("Please confirm the test card details.").className).not.toContain("desk-enter"),
    { timeout: 2_000 },
  );
  expect(trayCard("Please confirm the test card details.").className).toContain("desk-card-new");
});

it("(c2) load sequencing never reads as an arrival, however the queries order", async () => {
  const sources: Sources = {
    runs: [runFixture("parked", "awaiting_human", "2026-11-01T10:00:00Z", "Checkout test")],
    humanActions: [humanAction("ha-1", "Please log in so the tester can continue.", 4)],
    journeys: [],
    results: notReadyResults,
  };
  // The knowledge source settles while the page is still on its loading
  // panel (the browser's real ordering): the seen-set must not seed an
  // empty tray during that window.
  await mount(sources, { delayApps: true });
  const card = trayCard("Please log in so the tester can continue.");
  expect(card.className).not.toContain("desk-card-new");
  expect(card.className).not.toContain("desk-enter");
});

it("(d) reduced motion: same end states, statically — edge without travel", async () => {
  (window as { matchMedia?: unknown }).matchMedia = (query: string) => ({
    matches: query.includes("reduce"),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  });
  const sources: Sources = {
    runs: [
      runFixture("parked", "awaiting_human", "2026-11-01T10:00:00Z", "Checkout test"),
      runFixture("live", "running", "2026-11-03T10:00:00Z", "Live test"),
    ],
    humanActions: [humanAction("ha-1", "Please log in so the tester can continue.", 4)],
    journeys: [journey("j1", "Tom", 3), journey("j2", "Maya", 6)],
    results: notReadyResults,
  };
  const client = await mount(sources);

  sources.humanActions = [
    humanAction("ha-1", "Please log in so the tester can continue.", 4),
    humanAction("ha-2", "Please confirm the test card details.", 2),
  ];
  sources.journeys = [journey("j1", "Tom", 6), journey("j2", "Maya", 6)];
  await poll(client);

  const arrived = await waitFor(() => {
    const element = trayCard("Please confirm the test card details.");
    expect(element.className).toContain("desk-card-new");
    return element;
  });
  // The cue is the persistent static edge only: no enter classes, ever.
  expect(arrived.className).not.toContain("desk-enter");
  expect(document.querySelector("[data-desk-enter]")).toBeNull();
  // Bars render their true final length directly.
  expect((document.querySelector(".desk-step-fill") as HTMLElement).style.transform).toBe("scaleX(1)");
  expect(screen.getByText(/12 steps recorded so far/)).toBeInTheDocument();
});

it("the masthead crossfades only when the outgoing verdict was settled", async () => {
  const sources: Sources = {
    runs: [runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test")],
    humanActions: [],
    journeys: [],
    results: notReadyResults,
  };
  const client = await mount(sources);
  expect(await screen.findByRole("heading", { name: "Not ready yet", level: 2 })).toBeInTheDocument();
  // Let the outgoing verdict settle (the swap's 400ms settle rule).
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 500));
  });

  sources.results = readyResults;
  await poll(client);

  // During the crossfade both words exist: old fading out (in the
  // aria-hidden leaving copy), new fading in.
  await waitFor(() =>
    expect(document.querySelector(".desk-swap-leaving")?.textContent).toContain("Not ready yet"),
  );
  expect(screen.getByRole("heading", { name: "Ready", level: 2 })).toBeInTheDocument();
  // Then the old word is gone; the motion is finished and stays finished.
  await waitFor(() => expect(document.querySelector(".desk-swap-leaving")).toBeNull());
  expect(screen.queryByRole("heading", { name: "Not ready yet", level: 2 })).not.toBeInTheDocument();
});

it("archive rows entering on a filter change fade in (no stagger)", async () => {
  const sources: Sources = {
    runs: [
      runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test"),
      runFixture("failed", "failed", "2026-11-02T10:00:00Z", "Failed test"),
      runFixture("stopped", "cancelled", "2026-11-01T10:00:00Z", "Stopped test"),
    ],
    humanActions: [],
    journeys: [],
    results: notReadyResults,
  };
  await mount(sources);
  const section = screen.getByRole("region", { name: "RECENT TESTS" });
  fireEvent.click(within(section).getByRole("button", { name: /Failed · 1/ }));
  await waitFor(() => expect(within(section).queryByText(/Stopped test/)).not.toBeInTheDocument());
  fireEvent.click(within(section).getByRole("button", { name: /All · 3/ }));
  const entering = within(section).getByText(/Stopped test/).closest("article") as HTMLElement;
  expect(entering.className).toContain("desk-enter");
  expect(entering).toHaveAttribute("data-desk-enter");
});

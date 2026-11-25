import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { Finding, RunResults, TestRun } from "../../lib/api";
import { RunReportPage } from "./RunReportPage";
beforeEach(() => { vi.spyOn(api, "getRunJourneys").mockResolvedValue([]); });
afterEach(() => { vi.restoreAllMocks(); });

function renderReport(payload: Record<string, unknown>, findings: Finding[] = [], mode?: string, snapshot = {}, identity: Partial<TestRun> = {}, path = "/report") {
  const data: RunResults = {
    test_run_id: "run", findings,
    report: {
      id: "report", version: 1, status: "completed", generated_at: null,
      executive_summary: null, payload,
    },
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>
    <Routes><Route element={<Outlet context={{
      run: { id: "run", status: "completed", target_snapshot: {}, ...identity, configuration_snapshot: { ...snapshot, execution_mode: mode } },
      user: { id: "user" }, results: { status: "ready", data },
    }} />}><Route path="/report" element={<RunReportPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
}

const legacyNotice = "This report was produced by the older exploratory mode. Its findings are unverified observations.";

it("shows the watchdog reason and unfinished coverage when the UI audit has no report", () => {
  render(<MemoryRouter initialEntries={["/report"]}>
    <Routes><Route element={<Outlet context={{
      run: {
        status: "failed",
        status_reason: "The worker stopped this attempt after a period with no recorded progress.",
        configuration_snapshot: { slop_checkpoint: {
          visited: ["/", "/active"], pending: ["/queued"], in_flight: [{ url: "/active" }],
        } },
      },
      results: { status: "waiting" },
    }} />}><Route path="/report" element={<RunReportPage />} /></Route></Routes>
  </MemoryRouter>);
  expect(screen.getByText(/after a period with no recorded progress/)).toBeInTheDocument();
  expect(screen.getByText(/Final UI score unavailable/)).toHaveTextContent(
    "Page URLs processed: 1. Awaiting inspection or completion: 2.",
  );
});

it("uses the saved Board verdict and opens checks lazily from board.items", async () => {
  renderReport({ mode: "harness_v1", verdict: "Ready", market_verdict: { verdict: "not_ready" },
    board: { coverage: { checked: 1, denominator: 2 }, items: [
      { name: "Open details", effective_status: "worked", journey_id: "owned" },
      { name: "Search details", effective_status: "could_not_check", blocker: "Verify the effect before retrying." },
    ] }, items: [{ name: "Retired duplicate" }] }, [], undefined, { discovery_frontier: { pending: ["/stale"] } });
  expect(screen.getByRole("heading", { name: "Ready" })).toBeInTheDocument();
  expect(screen.getByText(/For shipping:/)).toHaveTextContent("Not ready yet");
  expect(screen.getByText(/Checked 1 of 2 eligible checks/)).toBeInTheDocument();
  expect(screen.queryByText("Retired duplicate")).not.toBeInTheDocument();
  expect(screen.queryByText(/Verify the effect before retrying/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Search details"));
  expect(await screen.findByText(/Verify the effect before retrying/)).toBeInTheDocument();
  expect(screen.getByText("No assertions were recorded for this check")).toBeInTheDocument();
});

it("reports an unknown verdict without deriving one from coverage", () => {
  renderReport({ mode: "harness_v1", board: { coverage: { checked: 2, denominator: 2 } } });
  expect(screen.getByRole("heading", { name: "No verdict recorded in this report" })).toBeInTheDocument();
  expect(screen.queryByText("Ready")).not.toBeInTheDocument();
});

it("keeps Explore counts aligned with the displayed Board checks", () => {
  renderReport({ mode: "harness_v1", verdict: "Ready", board: {
    coverage: { checked: 18, denominator: 18, counts: { worked: 18 } },
    items: [
      { name: "Open the menu", effective_status: "worked" },
      { name: "Open the settings", effective_status: "worked" },
      { name: "Save the settings", effective_status: "broken" },
    ],
  } });
  expect(screen.getByRole("heading", { name: "Ready" })).toBeVisible();
  expect(screen.queryByText(/18 eligible checks/)).toBeNull();
  expect(screen.getByText("3 checks were recorded. Coverage is not available.")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /Worked.*2/ }));
  const checks = screen.getByRole("heading", { name: "Checks" }).closest("section")!;
  expect(within(checks).getAllByRole("listitem")).toHaveLength(2);
  expect(within(checks).queryByText("Save the settings")).toBeNull();
});

it("applies a linked Explore outcome filter to the saved checks", () => {
  renderReport({ mode: "harness_v1", board: { items: [
    { name: "Worked check", effective_status: "worked" },
    { name: "Broken check", effective_status: "broken" },
  ] } }, [], undefined, {}, {}, "/report?outcome=broken");
  expect(screen.getByText("Showing: Broken")).toBeVisible();
  expect(screen.getByText("Broken check")).toBeVisible();
  expect(screen.queryByText("Worked check")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(screen.getByText("Worked check")).toBeVisible();
});

it.each([undefined, "legacy_persona"])("labels %s historical exploratory reports", (mode) => {
  renderReport({}, [], mode);
  expect(screen.getByRole("note")).toHaveTextContent(legacyNotice);
  expect(screen.getByText("Technical details").closest("details")).not.toHaveAttribute("open");
});

it.each(["deep_feature_v1", "discovery_contract_v1"])("does not label a %s report as legacy", (mode) => {
  renderReport({ mode }, [], mode);
  expect(screen.queryByText(legacyNotice)).not.toBeInTheDocument();
});

it.each([
  { journeys: ["journey"], href: "/runs/run/journeys/journey?step=8" },
  { journeys: ["first", "second"], href: "/runs/run/findings/issue" },
])("chooses evidence with the recorded journey association", ({ journeys, href }) => {
  renderReport({}, [{
    id: "issue", title: "The label is obscured", summary: "The saved image shows an obscured label.",
    category: "visual_criterion", severity: "high", status: "open", recommendation: null,
    finding_kind: "observed_product_issue", verification_status: "verified_visual",
    journey_ids: journeys, evidence: { step_ids: [8], artifact_ids: ["image"] },
  }]);
  const first = screen.getByRole("heading", { name: "What to check first" }).closest("section")!;
  expect(within(first).getByRole("link", { name: "View evidence" })).toHaveAttribute("href", href);
});

it("compares the previous report for the same target and withholds resolved claims for partial scope", async () => {
  const scope = { application_id: "app", target_id: "target", status: "completed" as const, configuration_snapshot: {} };
  vi.spyOn(api, "listRuns").mockResolvedValue([
    { ...scope, id: "wrong-target", target_id: "other", test_number: 19 },
    { ...scope, id: "previous", test_number: 18 },
  ] as TestRun[]);
  const repeated: Finding = {
    id: "this-finding", title: "Repeated issue", summary: "Saved issue", category: "functional",
    severity: "high", status: "open", recommendation: null, finding_kind: "observed_product_issue",
    verification_status: "verified_visual", journey_ids: [], evidence: { step_ids: [], artifact_ids: ["screenshot"] },
  };
  const prior = vi.spyOn(api, "getRunResults").mockResolvedValue({
    test_run_id: "previous",
    report: { id: "old-report", generated_at: null, status: "completed", version: 1, executive_summary: null, payload: {} },
    findings: [{ ...repeated, id: "old-finding" }, { ...repeated, id: "old-absent", title: "Could have been missed" }],
  });
  renderReport({ coverage: { partial: true } }, [repeated], undefined, {}, { ...scope, test_number: 20 });
  expect(await screen.findByRole("heading", { name: "Since the previous run" })).toBeInTheDocument();
  expect(prior.mock.calls[0][0]).toBe("previous");
  expect(screen.getByText("Still present · 1")).toBeInTheDocument();
  expect(screen.getByText("Not verified").parentElement).toHaveTextContent(/Resolved.*Not verified/);
  expect(screen.getByText(/Same target\. Resolved findings could not be verified/)).toBeVisible();
});

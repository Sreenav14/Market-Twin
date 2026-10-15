import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { FeatureCases } from "./FeatureCases";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("shows expected and observed values with the exact supporting step", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    available: true, evaluation_pending: false,
    coverage: { planned: 1, passed: 0, failed_assertions: 1, blocked: 0, inconclusive: 0, not_run: 0 },
    cases: [{ case_id: "email", title: "Invalid email", kind: "negative", verdict: "not_satisfied",
      journey_id: "journey-1", assertions: [{ assertion_id: "error", expected_value: "Email required",
        observed_value: "absent", status: "not_satisfied", step_id: 45, artifact_ids: [], origin: "fixture_truth" }] }],
  }), { status: 200, headers: { "Content-Type": "application/json" } })));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><FeatureCases runId="run-1" userId="user-1" /></MemoryRouter>
  </QueryClientProvider>);
  expect(await screen.findByRole("heading", { name: "Invalid email" })).toBeInTheDocument();
  expect(screen.getByText("Email required", { exact: true })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open supporting step" })).toHaveAttribute("href", "/runs/run-1/journeys/journey-1?step=45");
  expect(screen.getByText(/Next: open the supporting step/)).toBeInTheDocument();
});

it("keeps a recorded result unverified while evaluation is pending", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    available: true, evaluation_pending: true, coverage: null,
    cases: [{ case_id: "email", title: "Invalid email", kind: "negative", verdict: "awaiting_verification",
      recorded_verdict: "not_satisfied", journey_id: "journey-1", assertions: [{
        assertion_id: "error", expected_value: "Email required", observed_value: "absent",
        status: "not_satisfied", step_id: 45, artifact_ids: [], origin: "fixture_truth" }] }],
  }), { status: 200, headers: { "Content-Type": "application/json" } })));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><FeatureCases runId="run-1" userId="user-1" /></MemoryRouter>
  </QueryClientProvider>);
  expect(await screen.findByText(/Recorded result awaiting verification: not satisfied/)).toBeInTheDocument();
  expect(screen.getByText(/not a confirmed defect/)).toBeInTheDocument();
});

it("drills from the case list into assertion provenance without changing verdicts", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    available: true, evaluation_pending: false, coverage: null,
    cases: [
      { case_id: "email", title: "Invalid email", kind: "negative", verdict: "passed", journey_id: "journey-1", assertions: [{ assertion_id: "error", expected_value: "Email required", observed_value: "Email required", status: "passed", step_id: 3, artifact_ids: [], origin: "approved_requirement" }] },
      { case_id: "save", title: "Save profile", kind: "positive", verdict: "inconclusive", journey_id: "journey-2", assertions: [{ assertion_id: "saved", expected_value: true, observed_value: null, status: "inconclusive", step_id: 8, artifact_ids: [], origin: "inferred" }] },
    ],
  }), { status: 200, headers: { "Content-Type": "application/json" } })));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><FeatureCases runId="run-1" userId="user-1" /></MemoryRouter>
  </QueryClientProvider>);
  expect(await screen.findByRole("heading", { name: "Invalid email" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Save profile/ }));
  expect(screen.getByRole("heading", { name: "Save profile" })).toBeInTheDocument();
  expect(screen.getByText("inconclusive", { exact: true })).toBeInTheDocument();
  expect(screen.getByText("inferred", { exact: true })).toBeInTheDocument();
});

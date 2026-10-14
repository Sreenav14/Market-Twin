import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, cleanup } from "@testing-library/react";
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
  expect(await screen.findByText("Invalid email")).toBeInTheDocument();
  expect(screen.getByText(/Expected: Email required/)).toBeInTheDocument();
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

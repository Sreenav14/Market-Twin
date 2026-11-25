import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it } from "vitest";
import { RunOverviewPage } from "./RunOverviewPage";
import type { RunContext } from "../../layouts/RunLayout";

afterEach(cleanup);

function renderOverview(
  discoveryStage: string,
  status = "awaiting_human",
  results: RunContext["results"] = { status: "waiting", data: null, error: null },
  snapshot: Record<string, unknown> = {},
) {
  const context = {
    run: { id: "test", status, target_snapshot: {}, configuration_snapshot: {
      execution_mode: "discovery_contract_v1", discovery_stage: discoveryStage,
      ...snapshot,
    } }, results, user: { id: "user" }, workspace: { role: "member" },
  };
  return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><Routes><Route element={<Outlet context={context} />}>
    <Route path="/" element={<RunOverviewPage />} />
  </Route></Routes></MemoryRouter></QueryClientProvider>);
}

it("counts completed and in-flight pages separately and lists current audit URLs", () => {
  renderOverview("", "running", undefined, { execution_mode: "slop", slop_checkpoint: {
    visited: ["/product", "/blog"], pending: ["/help"], in_flight: [{ url: "/blog" }],
  } });
  const progress = within(screen.getByRole("region", { name: "UI audit progress" }));
  expect(progress.getByText(/Processed 1/)).toHaveTextContent("Processed 1 · In progress 1 · Queued 1");
  expect(progress.getByRole("listitem")).toHaveTextContent("/blog");
});

it("shows evidence from the submitted page while the audit is still running", () => {
  renderOverview("", "running", undefined, {
    slop_entry_assessment: {
      url: "https://app.test/product", viewports: ["desktop1280", "mobile320"], elements_judged: 3,
      findings_count: 1, findings: [{ detail: "Page overflows horizontally.", severity: "severe",
        viewports: ["mobile320"], artifact_ids: ["proof"] }],
    },
  });
  const assessment = within(screen.getByRole("region", { name: "Submitted page assessment" }));
  expect(assessment.getByText("Page overflows horizontally.")).toBeInTheDocument();
  expect(assessment.getByRole("button", { name: "View evidence" })).toBeInTheDocument();
});

it("shows the retired contract stage without an approval link", () => {
  renderOverview("awaiting_approval");
  expect(screen.queryByRole("link", { name: "Approve the tests" })).not.toBeInTheDocument();
});

it("links executing approved journeys to the canonical live view", () => {
  renderOverview("executing", "running");
  expect(screen.getByRole("link", { name: "Watch live" })).toHaveAttribute("href", "/runs/test/watch");
  expect(screen.getByRole("heading", { name: "Test in progress — findings so far" })).toBeInTheDocument();
});
it("shows a report error instead of an evaluation progress banner", () => {
  renderOverview("executing", "completed", {
    status: "error",
    data: null,
    error: "Report generation stopped. Ask your workspace operator to recover evaluation.",
  });
  expect(screen.getByText(/Report generation stopped/)).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Evaluation in progress/ })).toBeNull();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
});

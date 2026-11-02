import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { Finding, RunResults } from "../../lib/api";
import { RunReportPage } from "./RunReportPage";
beforeEach(() => { vi.spyOn(api, "getRunJourneys").mockResolvedValue([]); });
afterEach(() => { vi.restoreAllMocks(); });

function renderReport(payload: Record<string, unknown>, findings: Finding[] = []) {
  const data: RunResults = {
    test_run_id: "run", findings,
    report: {
      id: "report", version: 1, status: "completed", generated_at: null,
      executive_summary: null, payload,
    },
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/report"]}>
    <Routes><Route element={<Outlet context={{
      run: { id: "run", status: "completed", configuration_snapshot: {} },
      user: { id: "user" }, results: { status: "ready", data },
    }} />}><Route path="/report" element={<RunReportPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
}

it("shows an evidence limit for unknown scope and keeps method details available", () => {
  renderReport({});
  const result = screen.getByRole("region", { name: "Test result" });
  expect(within(result).getByText("Insufficient evidence")).toBeInTheDocument();
  expect(screen.queryByText("Verified Clean")).not.toBeInTheDocument();
  expect(screen.getByText("Scope, method and report identifiers").closest("details"))
    .not.toHaveAttribute("open");
  for (const link of within(screen.getByRole("navigation", { name: "Report findings" })).getAllByRole("link")) {
    expect(document.querySelector(link.getAttribute("href")!)).toBeInTheDocument();
  }
});

it("keeps a visual finding and its evidence link directly available after the compact result", () => {
  renderReport({ journeys: { total: 1, status_counts: { completed: 1 } } }, [{
    id: "issue", title: "The label is obscured", summary: "The saved image shows an obscured label.",
    category: "visual_criterion", severity: "high", status: "open", recommendation: null,
    finding_kind: "observed_product_issue", verification_status: "verified_visual",
    journey_ids: ["journey"], evidence: { step_ids: [8], artifact_ids: ["image"] },
  }]);
  const result = screen.getByRole("region", { name: "Test result" });
  expect(within(result).getByRole("heading", { name: "1 verified product issue" })).toBeInTheDocument();
  expect(within(result).getByText(/Recorded visual checks support/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Inspect step 8 evidence/ }))
    .toHaveAttribute("href", "/runs/run/journeys/journey?step=8");
  expect(screen.getByRole("link", { name: "1 verified issue" })).toHaveAttribute("href", "#report-verified");
});

it("does not invent a step-to-journey association for a finding spanning several journeys", () => {
  renderReport({}, [{
    id: "combined", title: "Repeated issue", summary: "Recorded across different journeys.",
    category: "visual_criterion", severity: "high", status: "open", recommendation: null,
    finding_kind: "observed_product_issue", verification_status: "verified_visual",
    journey_ids: ["first", "second"], evidence: { step_ids: [8], artifact_ids: ["image"] },
  }]);
  expect(screen.getByRole("link", { name: /Review linked evidence/ }))
    .toHaveAttribute("href", "/runs/run/findings/combined");
  expect(screen.queryByRole("link", { name: /Inspect step 8 evidence/ })).not.toBeInTheDocument();
});

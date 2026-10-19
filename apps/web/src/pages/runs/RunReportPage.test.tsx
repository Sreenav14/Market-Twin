import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";
import type { Finding, RunResults } from "../../lib/api";
import { RunReportPage } from "./RunReportPage";

function renderReport(payload: Record<string, unknown>, findings: Finding[] = []) {
  const data: RunResults = {
    test_run_id: "run", findings,
    report: {
      id: "report", version: 1, status: "completed", generated_at: null,
      executive_summary: null, payload,
    },
  };
  return render(<MemoryRouter initialEntries={["/report"]}>
    <Routes><Route element={<Outlet context={{
      run: { id: "run", status: "completed", configuration_snapshot: {} },
      user: { id: "user" }, results: { status: "ready", data },
    }} />}><Route path="/report" element={<RunReportPage />} /></Route></Routes>
  </MemoryRouter>);
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

import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it } from "vitest";
import type { RunContext } from "../../layouts/RunLayout";
import type { Finding, RunResults } from "../../lib/api";
import { RunFindingsPage } from "./RunFindingsPage";
import { RunOverviewPage } from "./RunOverviewPage";

afterEach(cleanup);
function mount(page: "findings" | "summary", findings: Finding[] = []) {
  const results: RunResults = { test_run_id: "run", findings, report: { id: "report", version: 1, status: "completed", generated_at: null, executive_summary: "Recorded summary", payload: { mode: "deep_feature_v1", coverage: { planned: 2, passed: 1, failed_assertions: 2, inconclusive: 0, blocked: 0, not_run: 0 }, cases: [{ assertions: [{ origin: "inferred" }, { origin: "inferred" }] }] } } };
  const context: RunContext = {
    run: { id: "run", workspace_id: "workspace", application_id: "application", target_id: "target", created_by_user_id: "operator", status: "completed", configuration_snapshot: { execution_mode: "deep_feature_v1" }, target_snapshot: {} },
    user: { id: "operator", email: "synthetic@example.test", normalized_email: "synthetic@example.test", display_name: null },
    workspace: { id: "workspace", name: "Synthetic workspace", status: "active", role: "owner" },
    results: { status: "ready", data: results, error: null }, refresh: () => {},
  };
  function Layout() { return <Outlet context={context} />; }
  render(<MemoryRouter><Routes><Route element={<Layout />}><Route path="*" element={page === "findings" ? <RunFindingsPage /> : <RunOverviewPage />} /></Route></Routes></MemoryRouter>);
}

it.each(["findings", "summary"] as const)("shows failed assertion coverage rather than implying a clean product on %s", (page) => {
  mount(page);
  expect(screen.getByRole("heading", { name: "No verified findings" })).toBeInTheDocument();
  expect(screen.getByText(/Assertions failed, but/)).toBeInTheDocument();
  expect(screen.getByText("Failed assertions").nextElementSibling).toHaveTextContent("2");
  expect(screen.getByText("Planner-inferred assertions").nextElementSibling).toHaveTextContent("2");
  if (page === "findings") expect(screen.getByRole("link", { name: "Review case outcomes and assertions" })).toHaveAttribute("href", "/runs/run/report#report-feature-cases");
});

it("renders a verified deterministic assertion finding in Confirmed issues", () => {
  mount("findings", [{ id: "finding", severity: "medium", category: "deterministic_assertion", finding_kind: "observed_product_issue", verification_status: "verified_deterministic", title: "Approved registration requirement failed", summary: "Recorded assertion evidence", recommendation: null, status: "open", journey_ids: ["journey"], evidence: { step_ids: [1], artifact_ids: ["artifact"] } }]);
  const confirmed = screen.getByRole("region", { name: "Confirmed issues" });
  expect(within(confirmed).getByRole("button", { name: /Approved registration requirement failed/ })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open finding details" })).toHaveAttribute("href", "/runs/run/findings/finding");
  expect(screen.queryByText("No verified findings")).not.toBeInTheDocument();
});

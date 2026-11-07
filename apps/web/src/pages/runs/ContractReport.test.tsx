import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import { ContractReport } from "./ContractReport";

beforeEach(() => {
  vi.spyOn(api, "getArtifactAccess").mockResolvedValue({
    artifact_id: "art-1", artifact_type: "screenshot", content_type: "image/png",
    url: "https://example.invalid/shot.png", expires_in_seconds: 600,
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it("keeps unconfirmed observations outside broken and shows verdict inputs", () => {
  render(<MemoryRouter><ContractReport runId="run" payload={{
    coverage: { tested_features: 2, discovered_features: 3 }, what_works: [], confirmed: [],
    unverified: [{ check: "Search did not finish", reason: "did_not_reproduce" }],
    market_verdict: { verdict: "insufficient_evidence", journeys_executed: 2, journeys_approved: 4,
      confirmed_defects: 0, persona_means: { Expert: 4.2 } },
  }} /></MemoryRouter>);
  const broken = screen.getByRole("region", { name: "What's broken" });
  expect(within(broken).queryByText(/Search did not finish/)).not.toBeInTheDocument();
  expect(screen.getByText(/Search did not finish — did not happen again on re-check/)).toBeInTheDocument();
  expect(screen.getByText("Coverage: tested 2 of 3 discovered features.")).toBeInTheDocument();
  expect(screen.getByText("Tested 2 of 4 approved journeys · 0 confirmed problems.")).toBeInTheDocument();
  expect(screen.queryByText(/Tester scores:/)).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Is it market-ready?" })).toBeInTheDocument();
});
it("attributes saved experience comments to the tester without displaying numeric feelings scores", () => {
  render(<MemoryRouter><ContractReport runId="run" payload={{
    experience: { personas: [{ persona_name: "Expert", status: "completed", facts: {},
      scores: { ease: { score: 4, justification: "I found the search controls easy to follow." } },
    }] },
  }} /></MemoryRouter>);
  expect(screen.getByText("I found the search controls easy to follow.").closest("blockquote"))
    .toHaveTextContent("— Expert, simulated tester");
  expect(screen.queryByText(/4\/5/)).not.toBeInTheDocument();
});
it("does not invent tested features when the API does not supply their count", () => {
  render(<MemoryRouter><ContractReport runId="run" payload={{ coverage: { executed: 5, discovered_features: 6 } }} /></MemoryRouter>);
  expect(screen.getByText("Coverage: tested unavailable of 6 discovered features.")).toBeInTheDocument();
});

// Mirrors the owner's MT-000113 export: 2 of 7 features, 1 confirmed break,
// 1 policy-blocked journey, three testers (Mobile blocked at 1 of 2).
const completedRunPayload = {
  coverage: { executed: 2, approved: 2, discovered_features: 7, tested_features: 2, verified_findings: 1 },
  journeys: [
    { journey_key: "explore_homepage", title: "Explore homepage and primary navigation", feature_key: "navigation",
      checks: [{ assertion_id: "a1", plain_language: "At step 1, button 'Products' is visible" }] },
    { journey_key: "review_pricing", title: "Review pricing options and calculator", feature_key: "pricing",
      checks: [{ assertion_id: "a3", plain_language: "Pricing tiers are listed with prices" }] },
  ],
  cases: [
    { journey_key: "explore_homepage", persona_index: 0, verdict: "not_satisfied" },
    { journey_key: "explore_homepage", persona_index: 1, verdict: "not_satisfied" },
    { journey_key: "explore_homepage", persona_index: 2, verdict: "satisfied" },
    { journey_key: "review_pricing", persona_index: 0, verdict: "unverified" },
    { journey_key: "review_pricing", persona_index: 1, verdict: "unverified" },
    { journey_key: "review_pricing", persona_index: 2, verdict: "not_run" },
  ],
  what_works: [], what_works_details: [],
  confirmed: [{ journey_key: "explore_homepage", assertion_id: "a1", finding_id: "finding-1",
    check: "At step 1, button 'Products' is visible", reason: "reproduced", verification: "verified_deterministic",
    artifact_ids: ["art-1"], screenshot_artifact_ids: ["art-1"] }],
  unverified: [{ journey_key: "review_pricing", reason: "policy_blocked", completed_steps: 0, planned_steps: 5 }],
  experience: { personas: [
    { persona_index: 0, persona_name: "First-time user", status: "completed",
      facts: { journeys_completed: 2, journeys_attempted: 2, total_steps: 19, failed_actions: 0, timeouts: 0, checks_passed: 6, checks_failed: 0 },
      scores: { clarity: { score: 4, justification: "The screenshots show clearly labeled navigation and product categories [checks_passed=6]." } } },
    { persona_index: 1, persona_name: "Experienced user", status: "completed",
      facts: { journeys_completed: 2, journeys_attempted: 2, total_steps: 19, failed_actions: 0, timeouts: 0, checks_passed: 6, checks_failed: 0 },
      scores: { ease: { score: 5, justification: "Both journeys were completed with no failed actions [journeys_completed=2] [failed_actions=0]." } } },
    { persona_index: 2, persona_name: "Mobile user", status: "unavailable",
      facts: { journeys_completed: 1, journeys_attempted: 2, total_steps: 8, failed_actions: 0, timeouts: 0, checks_passed: 3, checks_failed: 0 },
      scores: {} },
  ] },
  market_verdict: { verdict: "ready_with_issues", journeys_executed: 2, journeys_approved: 2, confirmed_defects: 1 },
};

function renderCompletedRun() {
  return render(<MemoryRouter><ContractReport runId="run" payload={completedRunPayload} /></MemoryRouter>);
}

it("leads with the verdict and its figures, not a text wall", () => {
  const { container } = renderCompletedRun();
  const firstPanel = container.querySelector(".contract-report > section");
  expect(firstPanel).toHaveAttribute("aria-labelledby", "contract-market");
  expect(within(firstPanel as HTMLElement).getByText("Ready with issues")).toBeInTheDocument();
  expect(within(firstPanel as HTMLElement).getByText("Tested 2 of 2 approved journeys · 1 confirmed problem.")).toBeInTheDocument();
  expect(screen.getByText("Most of the app was not reached — 5 of 7 features unchecked")).toBeInTheDocument();
  expect(screen.getByText("Plus 5 more discovered features that no approved test covers.")).toBeInTheDocument();
  expect(screen.getByText("Problems confirmed in 1 of 2 journeys")).toBeInTheDocument();
  expect(screen.getByText("Of 2 journeys: 0 worked, 1 broke, 1 could not be checked.")).toBeInTheDocument();
});

it("filters journeys and findings by outcome, states the filter in words, and clears on a second click", () => {
  renderCompletedRun();
  fireEvent.click(screen.getByRole("button", { name: /Broken: 1 of 2 journeys/ }));
  expect(screen.getByText(/Showing only journeys that broke — 1 of 2 journeys/)).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "What works" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Seen once — not confirmed" })).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "What's broken" })).toBeInTheDocument();
  expect(screen.queryByText("Review pricing options and calculator")).not.toBeInTheDocument();
  expect(screen.getAllByText("Explore homepage and primary navigation").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: /Broken: 1 of 2 journeys/ }));
  expect(screen.queryByText(/Showing only journeys that broke/)).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "What works" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Seen once — not confirmed" })).toBeInTheDocument();
});

it("badges confirmed problems as reproduced and seen-once items as a separate group", () => {
  renderCompletedRun();
  expect(screen.getByText("Failed again on re-check")).toBeInTheDocument();
  expect(screen.getByText(/1 confirmed problem — each was seen again on re-check/)).toBeInTheDocument();
  expect(screen.getByText("Seen once")).toBeInTheDocument();
  expect(screen.getByText(/1 seen once — not reproduced or not re-checkable/)).toBeInTheDocument();
});

it("shows testers as identical panels, most-blocked first, quotes cleaned of machine metric keys", () => {
  const { container } = renderCompletedRun();
  const panels = [...container.querySelectorAll(".tester-panel")].map(el => el.getAttribute("aria-label"));
  expect(panels).toEqual(["Mobile user", "First-time user", "Experienced user"]);
  expect(screen.getByText("The screenshots show clearly labeled navigation and product categories.")).toBeInTheDocument();
  expect(screen.getByText("Evidence · checks passed 6")).toBeInTheDocument();
  expect(screen.getByText("Evidence · journeys completed 2 · failed actions 0")).toBeInTheDocument();
  expect(container.textContent).not.toContain("[checks_passed=6]");
  expect(container.textContent).not.toContain("[journeys_completed=2]");
  expect(screen.getByText("Completed 1 of 2 journeys · 8 steps · 0 failed actions · 0 timeouts.")).toBeInTheDocument();
});

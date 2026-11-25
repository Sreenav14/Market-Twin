import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import { ContractReport } from "./ContractReport";
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

it("shows the stored verdict and separates frozen criterion failures from coverage gaps", () => {
  renderCompletedRun();
  const takeaway = screen.getByRole("region", { name: "Takeaway" });
  expect(within(takeaway).getByRole("heading", { name: "Ready, with issues" })).toBeInTheDocument();
  expect(within(takeaway).getByText("Confirmed defects").closest("div")).toHaveTextContent("1");
  expect(screen.getByText("Tested 2 of 7 discovered features.")).toBeInTheDocument();
  expect(screen.getByText(/button 'Products' is visible/).closest("li")).toHaveTextContent("Not met");
  expect(screen.getByText(/Pricing tiers are listed/).closest("li")).toHaveTextContent("Can't tell");
  expect(screen.getByText(/Pricing tiers are listed/).closest("li")).toHaveTextContent("Blocked by the safety policy");
});

it("opens tester and journey details on demand", async () => {
  renderCompletedRun();
  expect(screen.queryByRole("table", { name: "Tester by journey" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Tester by journey"));
  const matrix = await screen.findByRole("table", { name: "Tester by journey" });
  fireEvent.click(within(matrix).getByRole("button", { name: "Not run" }));
  fireEvent.click(screen.getByText("1 journeys"));
  expect(await screen.findByText("Review pricing options and calculator ·")).toBeInTheDocument();
});

it("attributes experience comments to the tester and drops the numeric score", async () => {
  renderCompletedRun();
  expect(screen.queryByText(/clearly labeled navigation/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Tester impressions"));
  const quote = await screen.findByText("The screenshots show clearly labeled navigation and product categories.");
  expect(quote.closest("blockquote")).toHaveTextContent("— First-time user, simulated tester");
  expect(screen.getByText("checks passed 6")).toBeInTheDocument();
  expect(screen.queryByText(/checks_passed=6|4\/5/)).not.toBeInTheDocument();
});

it("does not substitute for missing feature coverage or verdict", () => {
  render(<MemoryRouter><ContractReport runId="run" payload={{ coverage: { executed: 5, discovered_features: 6 } }} /></MemoryRouter>);
  expect(screen.getByText("Feature coverage was not recorded in this report.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "No verdict recorded in this report" })).toBeInTheDocument();
});
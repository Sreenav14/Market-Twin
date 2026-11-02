import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it } from "vitest";
import { ContractReport } from "./ContractReport";

afterEach(cleanup);
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
  expect(screen.getByText(/Tested 2 of 4 approved journeys · 0 confirmed problems · Tester scores: Expert 4.2/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Is it market-ready?" })).toBeInTheDocument();
});
it("does not invent tested features when the API does not supply their count", () => {
  render(<MemoryRouter><ContractReport runId="run" payload={{ coverage: { executed: 5, discovered_features: 6 } }} /></MemoryRouter>);
  expect(screen.getByText("Coverage: tested unavailable of 6 discovered features.")).toBeInTheDocument();
});

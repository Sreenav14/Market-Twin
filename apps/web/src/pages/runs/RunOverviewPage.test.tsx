import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it } from "vitest";
import { RunOverviewPage } from "./RunOverviewPage";

afterEach(cleanup);

function renderOverview(discoveryStage: string, status = "awaiting_human") {
  const context = {
    run: { id: "test", status, target_snapshot: {}, configuration_snapshot: {
      execution_mode: "discovery_contract_v1", discovery_stage: discoveryStage,
    } }, results: { status: "pending" },
  };
  return render(<MemoryRouter><Routes><Route element={<Outlet context={context} />}>
    <Route path="/" element={<RunOverviewPage />} />
  </Route></Routes></MemoryRouter>);
}

it("shows contract approval as the current discovery stage and links to the actual approval view", () => {
  renderOverview("awaiting_approval");
  expect(screen.getByRole("link", { name: "Approve the tests" })).toHaveAttribute("href", "/runs/test/contract");
  const lifecycle = screen.getByRole("list", { name: "Test lifecycle" });
  expect(within(lifecycle).getByText("Approve the tests").closest("li")).toHaveClass("stage-current");
  expect(within(lifecycle).getByText("Check the journeys").closest("li")).not.toHaveClass("stage-done");
});

it("links executing approved journeys to the canonical live view", () => {
  renderOverview("executing", "running");
  expect(screen.getByRole("link", { name: "Watch live" })).toHaveAttribute("href", "/runs/test/watch");
  const lifecycle = screen.getByRole("list", { name: "Test lifecycle" });
  expect(within(lifecycle).getByText("Check the journeys").closest("li")).toHaveClass("stage-current");
});

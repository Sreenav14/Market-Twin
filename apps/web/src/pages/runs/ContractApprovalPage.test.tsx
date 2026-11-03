import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { api, type TestContract } from "../../lib/api";
import type { RunContext } from "../../layouts/RunLayout";
import { ContractApprovalPage } from "./ContractApprovalPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
function draft(): TestContract {
  return { contract_id: "contract", test_run_id: "run", version: 1, status: "draft", journeys: [{
    journey_key: "search", title: "Search the catalog", feature_key: "catalog", excluded: false,
    steps: [{ action: "click", target: { role: "button", name: "Search" } }], safe_test_data_keys: [],
    assertions: [{ assertion_id: "results", oracle: "title", target_role: null, target_name: null,
      expected_value: "Results", plain_language: "After searching, the title is Results.",
      origin: null, source_step_ordinal: 1, excluded: false }],
  }] };
}
function renderPage(contract = draft(), depth = "medium") {
  vi.spyOn(api, "getRunPreflight").mockResolvedValue({ ready: true, checks: [] });
  vi.spyOn(api, "getTestContract").mockResolvedValue(contract);
  const context = { user: { id: "owner" }, workspace: { id: "workspace", role: "owner" }, refresh: vi.fn(),
    run: { id: "run", application_id: "app", target_id: "target", status: "awaiting_human",
      target_snapshot: { base_url: "https://example.test", allowed_origins: [{ scheme: "https", hostname: "example.test" }] },
      configuration_snapshot: { testing_depth: depth, discovery_map: { features: [{}], journeys: contract.journeys.map(j => ({ journey_key: j.journey_key, completed: true })) } } },
  } as unknown as RunContext;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Context() { return <Outlet context={context} />; }
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/run/contract"]}><Routes><Route element={<Context />}><Route path="/runs/:runId/contract" element={<ContractApprovalPage />} /><Route path="/runs/:runId/watch" element={<p>Tests running</p>} /></Route></Routes></MemoryRouter></QueryClientProvider>);
}
it("approves before starting and displays the authorized app address", async () => {
  const order: string[] = [];
  vi.spyOn(api, "approveTestContract").mockImplementation(async () => { order.push("approve"); return { ...draft(), status: "approved" }; });
  vi.spyOn(api, "startTestContract").mockImplementation(async () => { order.push("start"); return { ...draft(), status: "frozen" }; });
  renderPage();
  expect(await screen.findByText(/These tests run against: https:\/\/example.test/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Approve and run tests" }));
  expect(await screen.findByText("Tests running")).toBeInTheDocument();
  expect(order).toEqual(["approve", "start"]);
});
it("shows an honest zero-journey state with a way to explore again", async () => {
  renderPage({ ...draft(), journeys: [] });
  expect(await screen.findByText(/No journeys were completed/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Explore again" })).toHaveAttribute("href", "/applications/app/runs/new?target=target&mode=discovery_contract_v1");
  expect(screen.queryByRole("button", { name: "Approve and run tests" })).not.toBeInTheDocument();
});
it("explains completed journeys excluded by the selected depth", async () => {
  const base = draft().journeys[0];
  const journeys = Array.from({ length: 4 }, (_, index) => ({
    ...base,
    journey_key: `journey_${index}`,
    title: `Journey ${index + 1}`,
    assertions: base.assertions.map(assertion => ({ ...assertion, assertion_id: `check_${index}` })),
    excluded: index === 3,
  }));
  renderPage({ ...draft(), journeys }, "low");
  expect(await screen.findByText(/low testing depth allows up to 3 journeys/)).toBeInTheDocument();
  expect(screen.getByText("This completed journey is beyond the selected testing-depth limit and starts excluded.")).toBeInTheDocument();
});
it("saves checkbox exclusions before approval", async () => {
  const update = vi.spyOn(api, "updateContractJourney").mockResolvedValue({ ...draft(), version: 2 });
  renderPage();
  await screen.findByText("Search the catalog");
  await userEvent.click(screen.getByRole("checkbox", { name: "After searching, the title is Results." }));
  await waitFor(() => expect(update).toHaveBeenCalledOnce());
  expect(update.mock.calls[0][3].assertions?.[0].excluded).toBe(true);
});
it("requires check wording review after its expected result changes", async () => {
  const update = vi.spyOn(api, "updateContractJourney").mockResolvedValue({ ...draft(), version: 2 });
  renderPage();
  await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
  const expected = screen.getByLabelText("Expected result");
  await userEvent.clear(expected);
  await userEvent.type(expected, "Billing");
  expect(screen.getByRole("button", { name: "Save check" })).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent("Update the wording above");
  const wording = screen.getByLabelText("What should happen?");
  await userEvent.clear(wording);
  await userEvent.type(wording, "After searching, the title is Billing.");
  await userEvent.click(screen.getByRole("button", { name: "Save check" }));
  await waitFor(() => expect(update).toHaveBeenCalledOnce());
  const saved = update.mock.calls[0][3].assertions?.[0];
  expect(saved?.expected_value).toBe("Billing");
  expect(saved?.plain_language).toBe("After searching, the title is Billing.");
});

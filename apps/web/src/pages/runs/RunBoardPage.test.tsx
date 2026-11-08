import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { RunBoardPage } from "./RunBoardPage";
import { api } from "../../lib/api";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderBoard() {
  const context = {
    run: { id: "run-1", status: "completed", target_snapshot: {}, configuration_snapshot: {} },
    results: { status: "pending" },
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Routes>
          <Route element={<Outlet context={context} />}>
            <Route path="/" element={<RunBoardPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

it("renders counts, the checked-of-total line and item rows", async () => {
  vi.spyOn(api, "getRunBoard").mockResolvedValue({
    run_id: "run-1",
    run_status: "completed",
    run_kind: "explore_test",
    total: 3,
    counts: { worked: 2, broken: 1 },
    items: [
      { item_id: "i1", state_id: "s1", case_id: "c1", role: "button", name: "Save", status: "worked", blocker: null, attempts: 1, page_url: "https://example.test/app" },
      { item_id: "i2", state_id: "s1", case_id: "c2", role: "button", name: "Pay", status: "broken", blocker: null, attempts: 2, page_url: "https://example.test/app" },
      { item_id: "i3", state_id: "s1", case_id: "c3", role: "link", name: "Help", status: "worked", blocker: null, attempts: 1, page_url: "https://example.test/app" },
    ],
  });
  renderBoard();
  await waitFor(() => expect(screen.getByText(/Checked 3 of 3 items/)).toBeTruthy());
  expect(screen.getByText("Save")).toBeTruthy();
  expect(screen.getByText("Pay")).toBeTruthy();
  expect(screen.getByText("Broken")).toBeTruthy();
});

it("shows the honest empty state when the run has no board", async () => {
  vi.spyOn(api, "getRunBoard").mockRejectedValue(new Error("404"));
  renderBoard();
  await waitFor(() => expect(screen.getByText("This run has no board")).toBeTruthy());
});

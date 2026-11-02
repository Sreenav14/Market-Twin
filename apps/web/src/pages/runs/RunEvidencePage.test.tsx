import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import * as apiModule from "../../lib/api";
import { RunEvidencePage } from "./RunEvidencePage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function Context({ runId }: { runId: string }) {
  return <Outlet context={{ run: { id: runId }, user: { id: "user" } }} />;
}
function Page({ client, runId }: { client: QueryClient; runId: string }) {
  return <QueryClientProvider client={client}><MemoryRouter><Routes>
    <Route element={<Context runId={runId} />}><Route path="*" element={<RunEvidencePage />} /></Route>
  </Routes></MemoryRouter></QueryClientProvider>;
}

it("does not reuse a selected journey from a different test when the outlet context changes", async () => {
  const journeys = (ids: string[]) => ids.map((id) => ({ id, persona_name: id, mission_title: "Goal" })) as apiModule.JourneyExecution[];
  vi.spyOn(apiModule.api, "getRunJourneys").mockImplementation(async (id) =>
    journeys(id === "first" ? ["old-one", "old-two"] : ["new-journey"]));
  const request = vi.spyOn(apiModule, "request").mockResolvedValue({
    journey: { step_count: 0 }, artifacts: [], next_after_step: null, artifacts_truncated: false,
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { rerender } = render(<Page client={client} runId="first" />);
  await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Select journey evidence" }), "old-two");
  await waitFor(() => expect(request).toHaveBeenCalledWith(expect.stringContaining("/first/journeys/old-two?"), expect.anything()));
  rerender(<Page client={client} runId="second" />);
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Select journey evidence" })).toHaveValue("new-journey"));
  await waitFor(() => expect(request).toHaveBeenCalledWith(expect.stringContaining("/second/journeys/new-journey?"), expect.anything()));
  expect(request.mock.calls.some(([path]) => path.includes("/second/journeys/old-two"))).toBe(false);
});

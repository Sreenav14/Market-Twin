import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { RunContext } from "../../layouts/RunLayout";
import { request, type JourneyDetail } from "../../lib/api";
import { JourneyDetailPage } from "./JourneyDetailPage";

vi.mock("../../lib/api", async (original) => ({
  ...await original<typeof import("../../lib/api")>(), request: vi.fn(),
}));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

const journey: JourneyDetail["journey"] = {
  id: "journey", ordinal: 1, persona_name: "Researcher", persona_perspective: "New user",
  mission_title: "Read a guide", mission_objective: "Locate the installation guide",
  step_count: 2, artifact_count: 0, evidence_available: true, summary: null,
  success_criteria: [], execution_id: "execution", attempt_number: 1,
  execution_status: "completed", outcome: null, started_at: null, completed_at: null,
  error_message: null, result: null,
};
function page(id: number, next: number | null): JourneyDetail {
  return { journey, steps: [{ id, step_number: id === 1 ? 1 : 2, action_type: "click",
    action_summary: id === 1 ? "Open help" : "Read installation guide", status: "completed",
    observation_summary: null, started_at: null, completed_at: null }],
    artifacts: [], findings: [], next_after_step: next, artifacts_truncated: false };
}
function mount(search = "?step=202") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const context: RunContext = {
    run: { id: "run", workspace_id: "workspace", application_id: "application", target_id: "target",
      created_by_user_id: "operator", target_snapshot: {}, status: "completed", configuration_snapshot: {} },
    user: { id: "operator", email: "user@example.test", normalized_email: "user@example.test", display_name: null },
    workspace: { id: "workspace", name: "Workspace", status: "active", role: "owner" },
    results: { status: "waiting", data: null, error: null }, refresh: () => {},
  };
  function Layout() {
    const location = useLocation(), navigate = useNavigate();
    return <><button onClick={() => navigate(-1)}>Back in history</button>
      <output aria-label="Evidence location">{location.search}</output><Outlet context={context} /></>;
  }
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/runs/run/journeys/journey${search}`]}>
    <Routes><Route element={<Layout />}><Route path="/runs/:runId/journeys/:journeyId" element={<JourneyDetailPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
}

it("locates a linked step automatically and preserves selection in history", async () => {
  vi.mocked(request).mockResolvedValueOnce(page(1, 1)).mockResolvedValueOnce(page(202, null));
  mount();
  const later = await screen.findByRole("button", { name: /Read installation guide/ });
  expect(later).toHaveAttribute("aria-pressed", "true");
  expect(request).toHaveBeenNthCalledWith(2,
    "/api/v1/test-runs/run/journeys/journey?after_step=1", expect.anything());
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /Open help/ }));
  expect(screen.getByLabelText("Evidence location")).toHaveTextContent("?step=1");
  await user.click(screen.getByRole("button", { name: "Back in history" }));
  await waitFor(() => expect(later).toHaveAttribute("aria-pressed", "true"));
});

it("reports a missing step after reaching the end without selecting unrelated evidence", async () => {
  vi.mocked(request).mockResolvedValueOnce(page(1, 1)).mockResolvedValueOnce(page(202, null));
  mount("?step=999");
  await screen.findByText(/This step was not found/);
  expect(request).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: /Open help/ })).toHaveAttribute("aria-pressed", "false");
});

it("keeps loaded evidence available after a later page fails and allows retry", async () => {
  vi.mocked(request).mockResolvedValueOnce(page(1, 1)).mockRejectedValueOnce(new Error("Unavailable"))
    .mockResolvedValueOnce(page(202, null));
  mount();
  const retry = await screen.findByRole("button", { name: "Retry loading steps" });
  expect(screen.getByRole("button", { name: /Open help/ })).toBeVisible();
  await userEvent.setup().click(retry);
  expect(await screen.findByRole("button", { name: /Read installation guide/ })).toHaveAttribute("aria-pressed", "true");
});

it("does not loop when the server returns a non-advancing cursor", async () => {
  vi.mocked(request).mockResolvedValueOnce(page(1, 0));
  mount("?step=999");
  await screen.findByText(/This step was not found/);
  expect(request).toHaveBeenCalledTimes(1);
});

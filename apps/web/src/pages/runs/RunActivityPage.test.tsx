import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { RunContext } from "../../layouts/RunLayout";
import { api, type ExecutionPause, type LiveExecution, type RunActivityItem } from "../../lib/api";
import { RunActivityPage } from "./RunActivityPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const item: RunActivityItem = { id: "step:1", run_id: "run", journey_id: "journey", execution_id: "execution", step_id: 1, source: "browser_agent", kind: "browser_action", status: "started", occurred_at: "2026-10-18T12:00:00Z", title: "Browser action recorded" };
function mount(role = "owner") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const context: RunContext = {
    run: { id: "run", workspace_id: "workspace", application_id: "application", target_id: "target", created_by_user_id: "operator", target_snapshot: {}, status: "running", configuration_snapshot: { study_brief: "Check registration", execution_mode: "legacy_persona" } },
    user: { id: "operator", email: "synthetic@example.test", normalized_email: "synthetic@example.test", display_name: null },
    workspace: { id: "workspace", name: "Synthetic workspace", status: "active", role },
    results: { status: "waiting", data: null, error: null }, refresh: () => {},
  };
  function Layout() { return <Outlet context={context} />; }
  render(<QueryClientProvider client={client}><MemoryRouter><Routes><Route element={<Layout />}><Route path="*" element={<RunActivityPage />} /></Route></Routes></MemoryRouter></QueryClientProvider>);
  return client;
}

it("merges cursor history by stable IDs and refreshes mutable statuses without duplicate activity", async () => {
  const user = userEvent.setup();
  let latest: LiveExecution = { run_id: "run", run_status: "running", server_observed_at: item.occurred_at, browser: null, activity: { items: [item], next_cursor: "opaque-cursor" } };
  vi.spyOn(api, "getLiveExecution").mockImplementation(async (_run, cursor) => cursor ? { ...latest, activity: { items: [item, { ...item, id: "event:older", title: "Planning recorded", source: "planner" }], next_cursor: null } } : latest);
  vi.spyOn(api, "getRunJourneys").mockResolvedValue([]);
  vi.spyOn(api, "listHumanActions").mockResolvedValue([]);
  vi.spyOn(api, "listActionApprovals").mockResolvedValue([]);
  const client = mount();
  await screen.findByText("Browser action recorded");
  await user.click(await screen.findByRole("button", { name: "Load older activity" }));
  await screen.findByText("Planning recorded");
  expect(screen.getAllByText("Browser action recorded")).toHaveLength(1);
  latest = { ...latest, activity: { items: [{ ...item, status: "completed" }], next_cursor: "new-latest-cursor" } };
  await client.invalidateQueries({ queryKey: ["live-execution"] });
  await waitFor(() => expect(screen.getByRole("button", { name: /Browser action recorded/ })).toHaveTextContent("completed"));
  expect(screen.getAllByText("Browser action recorded")).toHaveLength(1);
  expect(screen.getByText("Planning recorded")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Load older activity" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Browser action recorded/ }));
  expect(screen.getByRole("link", { name: "Inspect step 1 and supporting evidence" })).toHaveAttribute("href", "/runs/run/journeys/journey?step=1");
  expect(JSON.stringify(client.getQueryCache().getAll().map((query) => query.state.data))).not.toContain("blob:");
});

it("does not query privileged live metadata for a viewer role", async () => {
  const live = vi.spyOn(api, "getLiveExecution");
  const frames = vi.spyOn(api, "getLiveBrowserFrame");
  vi.spyOn(api, "getRunJourneys").mockResolvedValue([]);
  mount("viewer");
  expect(await screen.findByText(/Live activity and browser observation require owner/)).toBeInTheDocument();
  expect(live).not.toHaveBeenCalled();
  expect(frames).not.toHaveBeenCalled();
});

it("orders actual activity timestamps when ISO fractional precision differs", async () => {
  vi.spyOn(api, "getLiveExecution").mockResolvedValue({ run_id: "run", run_status: "running", server_observed_at: item.occurred_at, browser: null, activity: { items: [item, { ...item, id: "step:2", step_id: 2, occurred_at: "2026-10-18T12:00:00.100Z", title: "Later browser action" }], next_cursor: null } });
  vi.spyOn(api, "getRunJourneys").mockResolvedValue([]);
  vi.spyOn(api, "listHumanActions").mockResolvedValue([]);
  vi.spyOn(api, "listActionApprovals").mockResolvedValue([]);
  mount();
  await screen.findByText("Later browser action");
  const events = screen.getAllByRole("button").filter((button) => button.hasAttribute("aria-pressed"));
  expect(events[0]).toHaveTextContent("Later browser action");
  expect(events[1]).toHaveTextContent("Browser action recorded");
});

it("distinguishes accepted pause request from worker acknowledgement and fences takeover while resuming", async () => {
  const user = userEvent.setup();
  const pause: ExecutionPause = { id: "pause-1", status: "requested", execution_id: "execution", journey_id: "journey", browser_session_id: "browser", generation: 1, human_request_id: null, created_at: item.occurred_at, expires_at: "2026-10-18T12:05:00Z", acknowledged_at: null, completed_at: null };
  let latest: LiveExecution = { run_id: "run", run_status: "running", server_observed_at: item.occurred_at, browser: { browser_session_id: "browser", execution_id: "execution", journey_id: "journey", generation: 1, control_state: "agent", viewer_state: "available", journey_title: "Check registration", requesting_agent: "Persona" }, activity: { items: [], next_cursor: null } };
  vi.spyOn(api, "getLiveExecution").mockImplementation(async () => latest);
  vi.spyOn(api, "getLiveBrowserFrame").mockImplementation(() => new Promise(() => {}));
  vi.spyOn(api, "getRunJourneys").mockResolvedValue([]);
  const actions = vi.spyOn(api, "listHumanActions").mockResolvedValue([]);
  vi.spyOn(api, "listActionApprovals").mockResolvedValue([]);
  const request = vi.spyOn(api, "requestExecutionPause").mockImplementation(async () => { latest = { ...latest, pause }; return pause; });
  const resume = vi.spyOn(api, "resumeExecutionPause").mockImplementation(async () => { latest = { ...latest, pause: { ...pause, status: "resume_requested" } }; return latest.pause!; });
  const claim = vi.spyOn(api, "claimHumanAction");
  const client = mount();
  await waitFor(() => expect(screen.getByRole("button", { name: "Request pause" })).toBeEnabled());
  await user.click(screen.getByRole("button", { name: "Request pause" }));
  expect(request).toHaveBeenCalledWith("run", expect.objectContaining({ browser_session_id: "browser", generation: 1 }));
  await waitFor(() => expect(screen.getByRole("status", { name: "Manual pause status" })).toHaveTextContent("Pause requested; waiting"));
  expect(screen.queryByRole("button", { name: "Resume agent" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Take browser control/ })).not.toBeInTheDocument();
  latest = { ...latest, browser: { ...latest.browser!, control_state: "human_pending" }, pause: { ...pause, status: "paused", human_request_id: "request", acknowledged_at: item.occurred_at } };
  actions.mockResolvedValue([{ id: "request", test_run_id: "run", execution_id: "execution", browser_session_id: "browser", request_type: "other", status: "pending", created_at: item.occurred_at, expires_at: pause.expires_at, control_generation: 1, lease_id: null, lease_expires_at: null }]);
  await client.invalidateQueries({ queryKey: ["live-execution"] });
  await client.invalidateQueries({ queryKey: ["human-actions"] });
  expect(await screen.findByRole("button", { name: "Resume agent" })).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "Resume agent" }));
  expect(resume).toHaveBeenCalledWith("run", "pause-1");
  await waitFor(() => expect(screen.getByRole("status", { name: "Manual pause status" })).toHaveTextContent("Resume requested"));
  expect(screen.getByRole("button", { name: /Take browser control/ })).toBeDisabled();
  expect(claim).not.toHaveBeenCalled();
});

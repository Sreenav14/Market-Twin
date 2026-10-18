import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import type { RunContext } from "../../layouts/RunLayout";
import { HumanActionPage } from "./HumanActionPage";

vi.mock("./HumanBrowserViewer", () => ({
  HumanBrowserViewer: ({ autoConnect }: { autoConnect?: boolean }) => <p role="status">Protected browser viewer {autoConnect ? "connecting" : "waiting"}</p>,
}));

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it.each(["completed", "failed", "cancelled"])("explains an ended %s run with no human request", async (status) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(api, "listHumanActions").mockResolvedValue([]);
  vi.spyOn(api, "listActionApprovals").mockResolvedValue([]);
  const context = { run: { id: "run-1", status }, user: { id: "user-1" }, workspace: { id: "workspace-1", role: "owner" } } as unknown as RunContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/run-1/human-action"]}>
    <Routes><Route path="/runs/:runId" element={<ContextOutlet />}><Route path="human-action" element={<HumanActionPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole("heading", { name: "No human assistance was requested" })).toBeInTheDocument();
  expect(screen.queryByText("Waiting for the test")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Review execution and recorded evidence" })).toHaveAttribute("href", "/runs/run-1/journeys");
});

it("identifies the paused journey and does not offer control of a closed browser", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(api, "listHumanActions").mockResolvedValue([{
    id: "request-1", test_run_id: "run-1", execution_id: "execution-1", browser_session_id: "browser-1",
    request_type: "login", status: "pending", created_at: "2026-10-17T11:00:00Z", expires_at: null,
    control_generation: 0, lease_id: null, lease_expires_at: null,
    journey_id: "journey-1", journey_title: "Protected account", requesting_agent: "Persona agent",
    requested_by_step_id: 42, browser_state: "closed",
  }]);
  vi.spyOn(api, "listActionApprovals").mockResolvedValue([]);
  const context = { run: { id: "run-1", status: "awaiting_human" }, user: { id: "user-1" }, workspace: { id: "workspace-1", role: "owner" } } as unknown as RunContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/run-1/human-action"]}>
    <Routes><Route path="/runs/:runId" element={<ContextOutlet />}><Route path="human-action" element={<HumanActionPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  expect(await screen.findByText(/Requesting executor: Persona agent/)).toHaveTextContent("Protected account");
  expect(screen.getByRole("link", { name: "Inspect the paused journey at step 42" })).toHaveAttribute("href", "/runs/run-1/journeys/journey-1?step=42");
  expect(screen.getByRole("button", { name: /Take browser control/ })).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("no longer available");
});

it("explains recovery without claiming authentication was verified", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(api, "listHumanActions").mockResolvedValue([{
    id: "request-recovery", test_run_id: "run-1", execution_id: "execution-1",
    browser_session_id: "browser-1", request_type: "other", status: "completed",
    instructions: "Prepare the original control. Do not perform the pending action.",
    created_at: "2026-10-16T11:00:00Z", expires_at: null, control_generation: 2,
    lease_id: null, lease_expires_at: null,
  }]);
  vi.spyOn(api, "listActionApprovals").mockResolvedValue([]);
  const context = {
    run: { id: "run-1" }, user: { id: "user-1" },
    workspace: { id: "workspace-1", role: "owner" },
  } as unknown as RunContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={["/runs/run-1/human-action"]}>
    <Routes><Route path="/runs/:runId" element={<ContextOutlet />}><Route path="human-action" element={<HumanActionPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole("heading", { name: "Human assistance completed; resuming" }, { timeout: 3000 })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Authentication verified; resuming" })).not.toBeInTheDocument();
});

it("keeps lease secrets out of React Query cache across claim and release", async () => {
  const user = userEvent.setup();
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const lease = {
    request_id: "request-1", browser_session_id: "browser-1", lease_id: "lease-secret",
    lease_token: "lease-token-secret", generation: 1, expires_at: "2026-10-15T12:00:00Z",
    viewer_available: true, viewer_url: "wss://viewer.test/hitl", viewer_ticket: "viewer-ticket-secret",
  };
  vi.spyOn(api, "listHumanActions").mockResolvedValue([{
    id: "request-1", test_run_id: "run-1", execution_id: "execution-1", browser_session_id: "browser-1",
    request_type: "login", status: "pending", created_at: "2026-10-15T11:00:00Z", expires_at: lease.expires_at,
    control_generation: 0, lease_id: null, lease_expires_at: null,
  }]);
  vi.spyOn(api, "claimHumanAction").mockResolvedValue(lease);
  vi.spyOn(api, "listActionApprovals").mockResolvedValue([]);
  vi.spyOn(api, "releaseHumanAction").mockResolvedValue({ generation: 2 });
  const context = {
    run: { id: "run-1" }, user: { id: "user-1" }, workspace: { id: "workspace-1", role: "owner" },
  } as unknown as RunContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={["/runs/run-1/human-action"]}>
    <Routes><Route path="/runs/:runId" element={<ContextOutlet />}><Route path="human-action" element={<HumanActionPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);

  await user.click(await screen.findByRole("button", { name: /Take browser control/ }));
  expect(await screen.findByRole("heading", { name: "Controlling browser" })).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Protected browser viewer connecting");
  const cachedAfterClaim = JSON.stringify(queryClient.getMutationCache().getAll().map((mutation) => ({
    variables: mutation.state.variables, data: mutation.state.data,
  })));
  expect(cachedAfterClaim).not.toContain("lease-token-secret");
  expect(cachedAfterClaim).not.toContain("viewer-ticket-secret");

  await user.click(screen.getByRole("button", { name: "Done—resume agent" }));
  await waitFor(() => expect(api.releaseHumanAction).toHaveBeenCalledOnce());
  const cachedAfterRelease = JSON.stringify(queryClient.getMutationCache().getAll().map((mutation) => ({
    variables: mutation.state.variables, data: mutation.state.data,
  })));
  expect(cachedAfterRelease).not.toContain("lease-token-secret");
  expect(cachedAfterRelease).not.toContain("viewer-ticket-secret");
});

it("does not query or render human controls for a viewer role", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const listActions = vi.spyOn(api, "listHumanActions").mockResolvedValue([]);
  const listApprovals = vi.spyOn(api, "listActionApprovals").mockResolvedValue([]);
  const context = {
    run: { id: "run-1" }, user: { id: "viewer-1" }, workspace: { id: "workspace-1", role: "viewer" },
  } as unknown as RunContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={["/runs/run-1/human-action"]}>
    <Routes><Route path="/runs/:runId" element={<ContextOutlet />}><Route path="human-action" element={<HumanActionPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);

  expect(await screen.findByRole("status")).toHaveTextContent("Human browser control and action approvals require an owner or administrator role");
  expect(screen.queryByRole("button", { name: /Take browser control|Release control|Approve once|Reject/ })).not.toBeInTheDocument();
  await waitFor(() => {
    expect(listActions).not.toHaveBeenCalled();
    expect(listApprovals).not.toHaveBeenCalled();
  });
});

it.each([false, true])("skips only the blocked work while controlling=%s and clears local control after confirmation", async (controlling) => {
  const user = userEvent.setup();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const action = {
    id: "request-skip", test_run_id: "run-1", execution_id: "execution-1", browser_session_id: "browser-1",
    request_type: "login", status: "pending" as const, created_at: "2026-10-17T11:00:00Z", expires_at: null,
    control_generation: 0, lease_id: null, lease_expires_at: null,
  };
  const list = vi.spyOn(api, "listHumanActions").mockResolvedValue([action]);
  vi.spyOn(api, "listActionApprovals").mockResolvedValue([]);
  vi.spyOn(api, "claimHumanAction").mockResolvedValue({
    request_id: action.id, browser_session_id: "browser-1", lease_id: "lease-secret", lease_token: "token-secret",
    generation: 1, expires_at: "2026-10-17T12:00:00Z", viewer_available: false,
  });
  let confirmSkip: (() => void) | undefined;
  const skip = vi.spyOn(api, "skipHumanAction").mockImplementation(async () => {
    await new Promise<void>((resolve) => { confirmSkip = resolve; });
    list.mockResolvedValue([{ ...action, status: "skipped" }]);
    return { id: action.id, status: "skipped" };
  });
  const cancel = vi.spyOn(api, "cancelHumanAction");
  const release = vi.spyOn(api, "releaseHumanAction");
  const context = { run: { id: "run-1" }, user: { id: "user-1" }, workspace: { id: "workspace-1", role: "owner" } } as unknown as RunContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/run-1/human-action"]}>
    <Routes><Route path="/runs/:runId" element={<ContextOutlet />}><Route path="human-action" element={<HumanActionPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  if (controlling) {
    await user.click(await screen.findByRole("button", { name: /Take browser control/ }));
    await screen.findByRole("heading", { name: "Controlling browser" });
  }
  await user.click(await screen.findByRole("button", { name: "Skip this case/journey" }));
  expect(skip).toHaveBeenCalledWith(action.id);
  if (controlling) {
    expect(screen.getByRole("heading", { name: "Controlling browser" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done—resume agent" })).toBeDisabled();
  }
  confirmSkip?.();
  expect(await screen.findByRole("heading", { name: "Not tested—human assistance skipped" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Controlling browser" })).not.toBeInTheDocument();
  expect(cancel).not.toHaveBeenCalled();
  expect(release).not.toHaveBeenCalled();
  expect(JSON.stringify(client.getMutationCache().getAll().map((mutation) => mutation.state))).not.toContain("token-secret");
});

it("keeps local browser ownership visible when Skip delivery fails", async () => {
  const user = userEvent.setup();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(api, "listHumanActions").mockResolvedValue([{
    id: "request-1", test_run_id: "run-1", execution_id: "execution-1", browser_session_id: "browser-1",
    request_type: "login", status: "pending", created_at: "2026-10-17T11:00:00Z", expires_at: null,
    control_generation: 0, lease_id: null, lease_expires_at: null,
  }]);
  vi.spyOn(api, "listActionApprovals").mockResolvedValue([]);
  vi.spyOn(api, "claimHumanAction").mockResolvedValue({
    request_id: "request-1", browser_session_id: "browser-1", lease_id: "lease-1", lease_token: "token-1",
    generation: 1, expires_at: "2026-10-17T12:00:00Z", viewer_available: false,
  });
  vi.spyOn(api, "skipHumanAction").mockRejectedValue(new Error("Worker unavailable"));
  const context = { run: { id: "run-1" }, user: { id: "user-1" }, workspace: { id: "workspace-1", role: "owner" } } as unknown as RunContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/run-1/human-action"]}>
    <Routes><Route path="/runs/:runId" element={<ContextOutlet />}><Route path="human-action" element={<HumanActionPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await user.click(await screen.findByRole("button", { name: /Take browser control/ }));
  await screen.findByRole("heading", { name: "Controlling browser" });
  await user.click(screen.getByRole("button", { name: "Skip this case/journey" }));
  expect(await screen.findByText(/Skip could not be confirmed/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Controlling browser" })).toBeInTheDocument();
  expect(screen.queryByText("Not tested—human assistance skipped")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Skip this case/journey" })).toBeEnabled();
});

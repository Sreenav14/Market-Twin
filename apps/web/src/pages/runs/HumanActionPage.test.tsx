import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import type { RunContext } from "../../layouts/RunLayout";
import { HumanActionPage } from "./HumanActionPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

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
  const cachedAfterClaim = JSON.stringify(queryClient.getMutationCache().getAll().map((mutation) => ({
    variables: mutation.state.variables, data: mutation.state.data,
  })));
  expect(cachedAfterClaim).not.toContain("lease-token-secret");
  expect(cachedAfterClaim).not.toContain("viewer-ticket-secret");

  await user.click(screen.getByRole("button", { name: "Release control for verification" }));
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

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { AppShellContext } from "../../layouts/AppShell";
import { api, type TestRun } from "../../lib/api";
import { WorkspaceDashboardPage } from "./WorkspaceDashboardPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function runFixture(id: string, status: string, created_at: string, test_name: string): TestRun {
  return {
    id, status, created_at, workspace_id: "workspace", application_id: "app", target_id: "target",
    created_by_user_id: "user", target_snapshot: {}, configuration_snapshot: { test_name },
  } as TestRun;
}

async function mount(runs: TestRun[]) {
  vi.spyOn(api, "listApplications").mockResolvedValue([{ id: "app", workspace_id: "workspace", created_by_user_id: "user", name: "Fixture app", description: null, status: "active" }] as Awaited<ReturnType<typeof api.listApplications>>);
  vi.spyOn(api, "listRuns").mockResolvedValue(runs);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/dashboard"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/dashboard" element={<WorkspaceDashboardPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("heading", { name: "Dashboard", level: 1 });
}

it("links the needs-you row to the oldest awaiting_human run", async () => {
  await mount([
    runFixture("newer", "awaiting_human", "2026-11-02T10:00:00Z", "Newer parked test"),
    runFixture("oldest", "awaiting_human", "2026-11-01T10:00:00Z", "Oldest parked test"),
    runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test"),
  ]);
  const section = screen.getByRole("region", { name: "Needs your help" });
  expect(within(section).getByText(/Needs you — the tester is paused/)).toBeInTheDocument();
  expect(within(section).getAllByRole("link", { name: /Help this tester/ })[0]).toHaveAttribute("href", "/runs/oldest/human-action");
});

it("shows no needs-you row when no run is awaiting_human", async () => {
  await mount([runFixture("done", "completed", "2026-11-03T10:00:00Z", "Finished test")]);
  expect(screen.queryByText(/Needs you — the tester is paused/)).not.toBeInTheDocument();
});

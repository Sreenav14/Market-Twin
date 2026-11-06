import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { AppShellContext } from "./AppShell";
import { api } from "../lib/api";
import { RunLayout } from "./RunLayout";

vi.mock("../pages/runs/HumanActionPage", () => ({
  HumanAssistanceHost: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock("../components/markettwin/RunFlowPanel", () => ({ RunFlowPanel: () => null }));
vi.mock("../components/markettwin/RunPreflightPanel", () => ({ RunPreflightPanel: () => null }));

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("shows the needs-you banner with the run reason and a human-action link for a parked run", async () => {
  vi.spyOn(api, "getRun").mockResolvedValue({
    id: "run-1", workspace_id: "workspace", application_id: "app", target_id: "target", created_by_user_id: "user",
    status: "awaiting_human", status_reason: "Login required",
    target_snapshot: { name: "Fixture", environment: "production" },
    configuration_snapshot: { execution_mode: "harness_v1" },
  } as Awaited<ReturnType<typeof api.getRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as unknown as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/run-1/overview"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/runs/:runId" element={<RunLayout />}>
      <Route path="overview" element={<p>Overview body</p>} /></Route></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole("heading", { name: "Needs you — the tester is paused" })).toBeInTheDocument();
  expect(screen.getByText("Login required")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Help this tester" })).toHaveAttribute("href", "/runs/run-1/human-action");
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes, useOutletContext } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { AppShellContext } from "./AppShell";
import { ApiError, api } from "../lib/api";
import { RunLayout, type RunContext } from "./RunLayout";
import { ResultsBoundary } from "../components/markettwin/ResultsBoundary";

vi.mock("../pages/runs/HumanActionPage", () => ({
  HumanAssistanceHost: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock("../components/markettwin/RunFlowPanel", () => ({ RunFlowPanel: () => null }));
vi.mock("../components/markettwin/RunPreflightPanel", () => ({ RunPreflightPanel: () => null }));

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it.each([
  ["explore_test", "Explore & Test"],
  ["persona", "Persona Test"],
  ["slop", "Check the look"],
])("labels a native %s run using its current kind", async (runKind, label) => {
  vi.spyOn(api, "getRun").mockResolvedValue({
    id: "run-1", workspace_id: "workspace", application_id: "app", target_id: "target", created_by_user_id: "user",
    status: "running", run_kind: runKind,
    target_snapshot: { name: "Fixture", environment: "staging" },
    configuration_snapshot: {},
  } as Awaited<ReturnType<typeof api.getRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as unknown as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/run-1/overview"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/runs/:runId" element={<RunLayout />}>
      <Route path="overview" element={<p>Overview body</p>} /></Route></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  expect(await screen.findByText(`Fixture · staging · ${label}`)).toBeInTheDocument();
  client.clear();
});

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

it("moves pending evaluation to a recoverable error, then displays the recovered report", async () => {
  vi.spyOn(api, "getRun").mockResolvedValue({
    id: "run-1", workspace_id: "workspace", application_id: "app", target_id: "target", created_by_user_id: "user",
    status: "completed", target_snapshot: { name: "Fixture", environment: "production" },
    configuration_snapshot: { execution_mode: "harness_v1" },
  } as Awaited<ReturnType<typeof api.getRun>>);
  const getResults = vi.spyOn(api, "getRunResults")
    .mockRejectedValueOnce(new ApiError("Evaluation pending", 409))
    .mockRejectedValueOnce(new ApiError("Report generation stopped. Ask your workspace operator to recover evaluation.", 503))
    .mockResolvedValue({ findings: [] } as unknown as Awaited<ReturnType<typeof api.getRunResults>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as unknown as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  function Report() {
    const { results } = useOutletContext<RunContext>();
    return <ResultsBoundary>{results.status === "ready" ? <p>Recovered report</p> : null}</ResultsBoundary>;
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/run-1/results"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/runs/:runId" element={<RunLayout />}>
      <Route path="results" element={<Report />} /></Route></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole("heading", { name: "Preparing evaluation" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Check again" }));
  expect(await screen.findByText(/Report generation stopped/)).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Preparing evaluation" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Recovered report")).toBeInTheDocument();
  expect(getResults).toHaveBeenCalledTimes(3);
  client.clear();
});

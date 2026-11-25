import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Link, MemoryRouter, Outlet, Route, Routes, useOutletContext } from "react-router-dom";
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
    status: "running", run_kind: runKind, status_reason: "The test runner is offline.",
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
  expect(screen.getByRole("heading", { name: "Execution needs attention" })).toBeInTheDocument();
  expect(screen.getByText("The test runner is offline.")).toBeInTheDocument();
  client.clear();
});

it.each([["member", true], ["viewer", false]] as const)(
  "shows Start for a draft according to the %s role",
  async (role, canStart) => {
    vi.spyOn(api, "getRun").mockResolvedValue({
      id: "run-1", workspace_id: "workspace", application_id: "app", target_id: "target",
      status: "draft", target_snapshot: {}, configuration_snapshot: {},
    } as Awaited<ReturnType<typeof api.getRun>>);
    vi.spyOn(api, "getRunPreflight").mockResolvedValue({
      ready: false,
      checks: [{ name: "app_map", ready: false, reason: "The app map is still preparing.", advisory: false }],
    });
    const context = { user: { id: "user" }, workspace: { id: "workspace", role } } as unknown as AppShellContext;
    function ContextOutlet() { return <Outlet context={context} />; }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/run-1/overview"]}>
      <Routes><Route element={<ContextOutlet />}><Route path="/runs/:runId" element={<RunLayout />}>
        <Route path="overview" element={<p>Overview body</p>} /></Route></Route></Routes>
    </MemoryRouter></QueryClientProvider>);
    await screen.findByText("Overview body");
    if (canStart) {
      const start = screen.getByRole("button", { name: "Start test" });
      expect(start).toBeDisabled();
      act(() => client.setQueryData(["run-preflight", "user", "run-1"], {
        ready: true,
        checks: [{ name: "app_map", ready: true, reason: "Map preparation completed.", advisory: false }],
      }));
      await waitFor(() => expect(start).toBeEnabled());
    } else {
      expect(screen.queryByRole("button", { name: "Start test" })).not.toBeInTheDocument();
    }
    client.clear();
  },
);

it("shows a read-only replay draft with a fresh-test link and skips preflight", async () => {
  vi.spyOn(api, "getRun").mockResolvedValue({
    id: "legacy", workspace_id: "workspace", application_id: "app", target_id: "target",
    created_by_user_id: "user",
    status: "draft", target_snapshot: {},
    configuration_snapshot: { frozen_contract_source_run_id: "original" },
  });
  const preflight = vi.spyOn(api, "getRunPreflight");
  const start = vi.spyOn(api, "startRun");
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "member" } } as unknown as AppShellContext;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/legacy/overview"]}>
    <Routes><Route element={<Outlet context={context} />}><Route path="/runs/:runId" element={<RunLayout />}>
      <Route path="overview" element={<p>Stored overview</p>} /></Route></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  expect(await screen.findByText("Stored overview")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Contract replay retired" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Create a new test" })).toHaveAttribute(
    "href", "/applications/app/runs/new?mode=explore_test&target=target",
  );
  expect(screen.queryByRole("button", { name: "Start test" })).not.toBeInTheDocument();
  expect(preflight).not.toHaveBeenCalled();
  expect(start).not.toHaveBeenCalled();
  client.clear();
});

it("clears a rejected Start when visiting a different fresh draft and starts the new ID", async () => {
  const draft = (id: string): Awaited<ReturnType<typeof api.getRun>> => ({
    id, workspace_id: "workspace", application_id: "app", target_id: "target",
    created_by_user_id: "user",
    status: "draft", target_snapshot: {}, configuration_snapshot: {},
  });
  vi.spyOn(api, "getRun").mockImplementation(async (id) => draft(id));
  vi.spyOn(api, "getRunPreflight").mockResolvedValue({ ready: true, checks: [] });
  const start = vi.spyOn(api, "startRun")
    .mockRejectedValueOnce(new ApiError("The previous draft could not start.", 409))
    .mockResolvedValueOnce(draft("fresh"));
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "member" } } as unknown as AppShellContext;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/previous/overview"]}>
    <Routes><Route element={<Outlet context={context} />}><Route path="/runs/:runId" element={<RunLayout />}>
      <Route path="overview" element={<Link to="/runs/fresh/overview">Open fresh draft</Link>} />
      <Route path="watch" element={<p>Watching fresh draft</p>} />
    </Route></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  const firstStart = await screen.findByRole("button", { name: "Start test" });
  await waitFor(() => expect(firstStart).toBeEnabled());
  fireEvent.click(firstStart);
  expect(await screen.findByText("The previous draft could not start.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("link", { name: "Open fresh draft" }));
  const nextStart = await screen.findByRole("button", { name: "Start test" });
  await waitFor(() => expect(nextStart).toBeEnabled());
  expect(screen.queryByText("The previous draft could not start.")).not.toBeInTheDocument();
  fireEvent.click(nextStart);
  expect(await screen.findByText("Watching fresh draft")).toBeInTheDocument();
  expect(start.mock.calls).toEqual([["previous"], ["fresh"]]);
  client.clear();
});

it("shows the needs-you banner with the run reason and a Watch assistance link for a parked run", async () => {
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
  expect(screen.getByRole("link", { name: "Help this tester" })).toHaveAttribute("href", "/runs/run-1/watch#human-action-heading");
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

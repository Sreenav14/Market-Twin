import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { AppShellContext } from "../../layouts/AppShell";
import { api, type JourneyExecution, type TestRun } from "../../lib/api";
import { agentPrompts, type AgentPrompt } from "../../lib/agentPrompts";
import { AgentPromptsPage } from "./AgentPromptsPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it.each(["legacy_persona", "deep_feature_v1"])("shows actual goals, failed outcomes and evidence before advanced settings in %s", async (mode) => {
  const user = userEvent.setup();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(api, "getRun").mockResolvedValue({ id: "run", workspace_id: "workspace", application_id: "application", target_id: "target", created_by_user_id: "owner", target_snapshot: {}, status: "completed", configuration_snapshot: { execution_mode: mode } } as TestRun);
  vi.spyOn(api, "getRunJourneys").mockResolvedValue([{
    id: "journey", ordinal: 1, persona_name: "New visitor", persona_perspective: "A hypothetical first visit",
    mission_title: "Check registration", mission_objective: "Find a safe way to register", success_criteria: ["Registration opens"],
    execution_status: "completed", outcome: "failed", step_count: 3, artifact_count: 2,
  } as JourneyExecution]);
  vi.spyOn(agentPrompts, "list").mockResolvedValue({ test_run_id: "run", agents: [{
    snapshot: { id: "snapshot", agent_role: "meta", runtime_agent_name: "Test planner", model_name: "recorded-model", journey_id: null,
      created_at: "2026-10-18T12:00:00Z", snapshot_sha256: "sha", persona_snapshot: null, mission_snapshot: null },
    yaml: "instruction: Recorded instructions",
  } as AgentPrompt] });
  const context = { user: { id: "viewer" }, workspace: { id: "workspace", role: "viewer" } } as AppShellContext;
  function Layout() { return <Outlet context={context} />; }
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/run/agents"]}><Routes><Route element={<Layout />}><Route path="/runs/:runId/agents" element={<AgentPromptsPage />} /></Route></Routes></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByText("Check registration", { exact: true })).toBeInTheDocument();
  expect(screen.getByText("failed", { exact: true })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Inspect actions and evidence" })).toHaveAttribute("href", "/runs/run/journeys/journey");
  expect(screen.getByText("3 steps · 2 artifacts")).toBeInTheDocument();
  if (mode === "deep_feature_v1") expect(screen.getByRole("heading", { name: "Feature case 1" })).toBeInTheDocument();
  else expect(screen.getByRole("heading", { name: "New visitor · simulated tester" })).toBeInTheDocument();
  const advanced = screen.getByText("Advanced agent configuration and recorded diagnostics");
  expect(advanced.closest("details")).not.toHaveAttribute("open");
  await user.click(advanced);
  expect(await screen.findByLabelText("Prompt YAML")).toHaveValue("instruction: Recorded instructions");
  expect(screen.getByLabelText("Prompt YAML")).toHaveAttribute("readonly");
  expect(screen.queryByRole("button", { name: "Save prompt" })).not.toBeInTheDocument();
});

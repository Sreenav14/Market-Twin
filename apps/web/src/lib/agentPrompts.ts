import { request, type TestRun } from "./api";

export interface AgentConfiguration {
  name: string;
  agent_type: "LlmAgent" | "SequentialAgent";
  temperature: number;
  tools: string[];
  sub_agents: Array<AgentConfiguration & { instruction: string }>;
}
export interface AgentStructure {
  name: string;
  agent_type: string;
  sub_agents: AgentStructure[];
  model_configuration?: { requested_temperature?: number; temperature?: number | null };
  tools?: string[];
}

export interface AgentPrompt {
  available_tools?: string[];
  rerun_configuration?: AgentConfiguration;
  execution_started_at?: string | null;
  execution_completed_at?: string | null;
  duration_seconds?: number | null;
  saved_yaml?: string | null;
  saved_at?: string | null;
  snapshot: {
    id: string;
    agent_role: string;
    runtime_agent_name: string | null;
    model_name: string | null;
    journey_id: string | null;
    created_at: string;
    snapshot_sha256: string;
    persona_snapshot: { name?: string } | null;
    mission_snapshot: { name?: string } | null;
    model_configuration?: { requested_temperature?: number; temperature?: number | null };
    metadata?: { agent_structure?: AgentStructure };
  };
  yaml: string;
}

export const agentPrompts = {
  workspace: (workspaceId: string, fromDate: string, toDate: string, order: string, signal?: AbortSignal) => {
    const params = new URLSearchParams({ order });
    if (fromDate) params.set("created_after", new Date(`${fromDate}T00:00:00`).toISOString());
    if (toDate) {
      const end = new Date(`${toDate}T00:00:00`);
      end.setDate(end.getDate() + 1);
      params.set("created_before", end.toISOString());
    }
    return request<{ agents: Array<Omit<AgentPrompt, "yaml"> & { snapshot: AgentPrompt["snapshot"] & { test_run_id: string }; test_brief: string }>; limit: number }>(
      `/api/v1/workspaces/${workspaceId}/agent-prompts?${params}`, { signal },
    );
  },
  save: (runId: string, snapshotId: string, yaml: string, configuration?: AgentConfiguration) =>
    request<{ prompt_yaml: string; updated_at: string }>(
      `/api/v1/test-runs/${runId}/agent-prompts/${snapshotId}/draft`, {
        method: "PUT", body: JSON.stringify({ prompt_yaml: yaml, agent_configuration: configuration }),
      },
    ),
  list: (runId: string, signal?: AbortSignal) =>
    request<{ test_run_id: string; agents: AgentPrompt[] }>(
      `/api/v1/test-runs/${runId}/agent-prompts`, { signal },
    ),
  rerun: (runId: string, snapshotId: string, yaml: string, configuration?: AgentConfiguration) =>
    request<TestRun>(`/api/v1/test-runs/${runId}/agent-reruns`, {
      method: "POST",
      body: JSON.stringify({ snapshot_id: snapshotId, prompt_yaml: yaml, agent_configuration: configuration }),
    }),
};

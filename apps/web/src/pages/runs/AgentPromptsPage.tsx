import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import type { AppShellContext } from "../../layouts/AppShell";
import { agentPrompts, type AgentPrompt } from "../../lib/agentPrompts";
import { AgentTree } from "../../components/markettwin/AgentTree";
import { ProjectAgentBrowser } from "../../components/markettwin/ProjectAgentBrowser";
import { canWriteWorkspace } from "../../lib/permissions";
import { api } from "../../lib/api";

function createdDate(value: string) {
  const date = new Date(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function durationLabel(agent: Pick<AgentPrompt, "duration_seconds" | "execution_started_at" | "execution_completed_at">) {
  if (agent.duration_seconds != null) return `${agent.duration_seconds.toFixed(1)} seconds`;
  if (agent.execution_started_at && !agent.execution_completed_at) {
    const elapsed = Math.max(0, (Date.now() - new Date(agent.execution_started_at).getTime()) / 1000);
    return `Running · about ${Math.floor(elapsed)} seconds elapsed`;
  }
  return "Duration not recorded";
}

function PromptEditor({ agent, runId, writable, onSaved }: { agent: AgentPrompt; runId: string; writable: boolean; onSaved: (yaml: string, updatedAt: string) => void }) {
  const navigate = useNavigate();
  const [savedYaml, setSavedYaml] = useState(agent.saved_yaml || agent.yaml);
  const [yaml, setYaml] = useState(savedYaml);
  const [savedAt, setSavedAt] = useState(agent.saved_at || "");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [pendingLabel, setPendingLabel] = useState("");
  const supported = ["meta", "persona"].includes(agent.snapshot.agent_role);
  const dirty = yaml !== savedYaml;
  async function savePrompt() {
    setPendingLabel("Saving prompt…");
    setPending(true);
    setError("");
    try {
      const saved = await agentPrompts.save(runId, agent.snapshot.id, yaml);
      setSavedYaml(saved.prompt_yaml);
      setYaml(saved.prompt_yaml);
      setSavedAt(saved.updated_at);
      onSaved(saved.prompt_yaml, saved.updated_at);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save the prompt.");
    } finally {
      setPending(false);
    }
  }
  async function createRerun() {
    setPendingLabel("Creating rerun draft…");
    setPending(true);
    setError("");
    try {
      const draft = await agentPrompts.rerun(runId, agent.snapshot.id, yaml);
      navigate(`/runs/${draft.id}/overview`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the rerun.");
    } finally {
      setPending(false);
    }
  }
  return (
    <section className="agent-prompt-editor panel" aria-label="Agent prompt editor">
      <div className="agent-prompt-heading">
        <div>
          <h2>{agent.snapshot.runtime_agent_name || agent.snapshot.agent_role}</h2>
          <p className="muted">{agent.snapshot.mission_snapshot?.name || (agent.snapshot.agent_role === "meta" ? "Planning instructions" : "Recorded runtime context")} · {agent.snapshot.model_name || "Model not recorded"}</p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => {
          const url = URL.createObjectURL(new Blob([yaml], { type: "application/yaml" }));
          const link = document.createElement("a");
          link.href = url;
          link.download = `agent-${agent.snapshot.id}.yaml`;
          link.click();
          URL.revokeObjectURL(url);
        }}>Download YAML</Button>
      </div>
      <h3>Recorded execution structure</h3>
      <AgentTree structure={agent.snapshot.metadata?.agent_structure || { name: agent.snapshot.runtime_agent_name || "Recorded agent", agent_type: "LlmAgent", sub_agents: [], model_configuration: agent.snapshot.model_configuration }} />
      <p className="inline-note">{supported ? <>Edit <code>instruction</code>, <code>runtime_prompt</code>, and <code>rerun_configuration</code> in YAML, then save. Names, temperature, approved tools, and additional agents are configured only in YAML. Sequential subagents run in their listed order. Model, tools, persona and mission identify the original agent and are read-only. A rerun creates a new test draft for you to start, using the currently configured model.</> : "Recorded context for this runtime is read-only. Prompt reruns are available for planner and persona agents."}</p>
      <label className="field" htmlFor="agent-yaml">Prompt YAML</label>
      <textarea id="agent-yaml" className="text-input agent-yaml-input" value={yaml} onChange={(event) => setYaml(event.target.value)} spellCheck={false} readOnly={!writable || !supported} />
      {error ? <p className="error-text" role="alert">{error}</p> : null}
      <div className="agent-prompt-actions">
        <Button variant="secondary" disabled={pending || !dirty} onClick={() => { setYaml(savedYaml); setError(""); }}>Reset edits</Button>
        {writable && supported ? <>
          <Button variant="secondary" disabled={pending || !dirty || !yaml.trim()} onClick={() => void savePrompt()}>Save prompt</Button>
          <Button disabled={pending || dirty || !yaml.trim()} onClick={() => void createRerun()}>Create rerun draft</Button>
        </> : null}
      </div>
      <p className="muted" role="status">{pending ? pendingLabel : dirty ? "Unsaved changes. Save before creating a rerun." : savedAt ? `Prompt saved ${new Date(savedAt).toLocaleString()}.` : "Showing the original saved agent prompt."}</p>
      <p className="muted agent-prompt-history">Created {new Date(agent.snapshot.created_at).toLocaleString()} · {durationLabel(agent)}. Original snapshot {agent.snapshot.id.slice(0, 8)}. Existing prompts, results and evidence stay saved.</p>
    </section>
  );
}

export function AgentPromptsPage() {
  const queryClient = useQueryClient();
  const { workspace, user } = useOutletContext<AppShellContext>();
  const { runId } = useParams();
  const [params] = useSearchParams();
  const [selectedId, setSelectedId] = useState(params.get("snapshot") || "");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const run = useQuery({ queryKey: ["run", user.id, runId], queryFn: ({ signal }) => api.getRun(runId!, signal), enabled: Boolean(runId) });
  const journeys = useQuery({
    queryKey: ["agent-journeys", user.id, workspace.id, runId],
    queryFn: ({ signal }) => api.getRunJourneys(runId!, signal), enabled: Boolean(runId),
    refetchInterval: run.data && ["planning", "running", "awaiting_human"].includes(run.data.status) ? 3000 : false,
  });
  const state = useQuery({
    queryKey: ["agent-prompts", user.id, runId],
    queryFn: ({ signal }) => agentPrompts.list(runId!, signal),
    enabled: Boolean(runId),
    refetchInterval: run.data && ["planning", "running"].includes(run.data.status) ? 5_000 : false,
  });
  useEffect(() => {
    const available = state.data?.agents || [];
    if (available.length && !available.some((agent) => agent.snapshot.id === selectedId)) {
      const newest = [...available].sort((left, right) => new Date(right.snapshot.created_at).getTime() - new Date(left.snapshot.created_at).getTime())[0];
      setSelectedId(newest.snapshot.id);
    }
  }, [state.data?.agents, selectedId]);
  if (!runId) return <ProjectAgentBrowser workspaceId={workspace.id} />;
  const agents = state.data?.agents || [];
  const visibleAgents = agents.filter((agent) => {
    const date = createdDate(agent.snapshot.created_at);
    return (!fromDate || date >= fromDate) && (!toDate || date <= toDate);
  }).sort((left, right) => new Date(left.snapshot.created_at).getTime() - new Date(right.snapshot.created_at).getTime());
  const selected = agents.find((agent) => agent.snapshot.id === selectedId) || visibleAgents[0] || agents[0];
  function agentChoice(agent: AgentPrompt) {
    return <button className={`agent-prompt-choice${selected?.snapshot.id === agent.snapshot.id ? " is-selected" : ""}`} key={agent.snapshot.id} type="button" aria-pressed={selected?.snapshot.id === agent.snapshot.id} onClick={() => setSelectedId(agent.snapshot.id)}>
      <strong>{agent.snapshot.runtime_agent_name || agent.snapshot.agent_role}</strong>
      <span>{agent.snapshot.metadata?.agent_structure?.agent_type || "LlmAgent"} · {agent.snapshot.mission_snapshot?.name || agent.snapshot.agent_role.replaceAll("_", " ")}</span>
      <span>{new Date(agent.snapshot.created_at).toLocaleString()} · {durationLabel(agent)}</span>
    </button>;
  }
  return (
    <>
      <PageHeader title="Testers, goals and execution" description="See what was attempted and what the recorded evidence supports. Simulated testers are hypothetical perspectives, not human research participants." />
      <Link className="back-link" to="/agents">All projects</Link>
      <section className="tester-journeys" aria-label="Testers and goals">
        <h2>{run.data?.configuration_snapshot.execution_mode === "deep_feature_v1" ? "Feature Cases — deterministic execution" : "Simulated testers and journeys"}</h2>
        {journeys.isPending ? <LoadingPanel label="Loading recorded work" /> : journeys.isError ? <ErrorPanel message={journeys.error.message} /> : !journeys.data.length ? <p>No testing work has been recorded. Start the test to create its plan.</p> : journeys.data.map((journey) => <article className="tester-journey" key={journey.id}>
          <div><h3>{journey.runtime_name === "browser_discovery_v1" ? "Browser discovery" : run.data?.configuration_snapshot.execution_mode === "deep_feature_v1" ? `Feature case ${journey.ordinal}` : `${journey.persona_name} · simulated tester`}</h3>
            <strong>{journey.mission_title}</strong><p>{journey.mission_objective}</p>
            <details><summary>Success criteria and scenario</summary><ul>{journey.success_criteria.map((criterion, index) => <li key={index}>{criterion}</li>)}</ul><p>{journey.persona_perspective}</p></details>
          </div>
          <dl className="definition-list"><div><dt>Execution</dt><dd>{journey.execution_status?.replaceAll("_", " ") ?? "Not started"}</dd></div><div><dt>Recorded outcome</dt><dd>{journey.outcome ?? "Not established"}</dd></div><div><dt>Recorded work</dt><dd>{journey.step_count} steps · {journey.artifact_count} artifacts</dd></div></dl>
          <div className="button-row"><Link className="text-link" to={`/runs/${runId}/activity`}>Watch / assist</Link><Link className="text-link" to={`/runs/${runId}/journeys/${journey.id}`}>Inspect actions and evidence</Link></div>
        </article>)}
        <p className="muted">Execution completion and the product outcome are separate. A failed test is not automatically a confirmed website defect. Inspect its criteria and supporting evidence.</p>
      </section>
      <details className="tester-advanced"><summary>Advanced agent configuration and recorded diagnostics</summary>
      {state.isPending ? <LoadingPanel label="Loading agent prompts" /> : state.isError ? <ErrorPanel message={state.error.message} action={<Button variant="secondary" onClick={() => void state.refetch()}>Try again</Button>} /> : selected ? (
        <div className="agent-prompts-layout">
          <section className="panel agent-prompt-list" aria-label="Created agents">
            <h2>Agent flow <span className="muted">{agents.length}</span></h2>
            <div className="agent-date-filters">
              <label>Created from<input className="text-input" type="date" aria-label="Agents created from" value={fromDate} onChange={(event) => setFromDate(event.target.value)} /></label>
              <label>Created through<input className="text-input" type="date" aria-label="Agents created through" value={toDate} min={fromDate || undefined} onChange={(event) => setToDate(event.target.value)} /></label>
            </div>
            {!visibleAgents.length ? <p className="muted">No agents match these dates.</p> : null}
            {!visibleAgents.some((agent) => agent.snapshot.id === selected.snapshot.id) ? <p className="inline-note">The selected agent is outside these dates. Its editor stays open.</p> : null}
            <div className="agent-flow-scroll" tabIndex={0} aria-label="Test execution stages">
              <section className="agent-flow-stage"><h3>Meta Agent</h3>{visibleAgents.filter((agent) => agent.snapshot.agent_role === "meta").map(agentChoice)}
                {!agents.some((agent) => agent.snapshot.agent_role === "meta") ? <p className="muted">Planning prompt appears when recorded.</p> : null}
              </section>
              <section className="agent-flow-stage"><h3>Sequential Agent</h3><p className="muted">Journey subagents run one after another.</p>
                {visibleAgents.filter((agent) => agent.snapshot.agent_role === "persona").map(agentChoice)}
                {!agents.some((agent) => agent.snapshot.agent_role === "persona") ? <p className="muted">Subagents appear as journeys start.</p> : null}
              </section>
              <section className="agent-flow-stage"><h3>Collector</h3><p className="muted">Validates and collects committed journey results. Deterministic stage; no LLM prompt.</p></section>
              <section className="agent-flow-stage"><h3>Evaluation and Report</h3><p className="muted">Checks browser evidence before producing the report.</p>
                {visibleAgents.filter((agent) => !["meta", "persona"].includes(agent.snapshot.agent_role)).map(agentChoice)}
              </section>
            </div>
          </section>
          <PromptEditor key={selected.snapshot.id} agent={selected} runId={runId} writable={canWriteWorkspace(workspace.role)} onSaved={(yaml, updatedAt) => {
            void queryClient.invalidateQueries({ queryKey: ["agent-prompts", user.id, runId] });
            queryClient.setQueryData<{ test_run_id: string; agents: AgentPrompt[] }>(["agent-prompts", user.id, runId], (previous) => previous ? {
              ...previous, agents: previous.agents.map((agent) => agent.snapshot.id === selected.snapshot.id ? { ...agent, saved_yaml: yaml, saved_at: updatedAt } : agent),
            } : previous);
          }} />
        </div>
      ) : <EmptyState title="No agents have been created yet" copy="The planner appears when planning starts. Persona agents appear as their journeys start executing." />}
      </details>
    </>
  );
}

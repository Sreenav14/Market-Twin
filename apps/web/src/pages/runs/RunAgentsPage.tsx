import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";
import { Bot, Braces, Cpu, Gauge } from "lucide-react";
import { RunContext } from "../../layouts/RunLayout";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/results";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(value);
}

function roleLabel(role: string) {
  if (role === "meta") return "Meta Agent";
  if (role === "persona") return "Persona Agent";
  if (role === "visual_verifier") return "Visual Verifier";
  return role.replaceAll("_", " ");
}

export function RunAgentsPage() {
  const { run } = useOutletContext<RunContext>();
  const [params, setParams] = useSearchParams();

  const agentsQuery = useQuery({
    queryKey: ["run-agents", run.id],
    queryFn: ({ signal }) => api.listRunAgents(run.id, signal),
    refetchInterval:
      run.status === "running" || run.status === "planning" ? 5_000 : false,
  });

  const selectedId = useMemo(() => {
    const requested = params.get("agent");
    if (requested && agentsQuery.data?.some((agent) => agent.id === requested)) {
      return requested;
    }
    return agentsQuery.data?.[0]?.id ?? null;
  }, [agentsQuery.data, params]);

  const detailQuery = useQuery({
    queryKey: ["run-agent", run.id, selectedId],
    enabled: selectedId !== null,
    queryFn: ({ signal }) => api.getRunAgent(run.id, selectedId as string, signal),
  });

  if (agentsQuery.isPending) return <LoadingPanel label="Loading agents" />;
  if (agentsQuery.isError) return <ErrorPanel message={agentsQuery.error.message} />;

  const agents = agentsQuery.data;

  if (agents.length === 0) {
    return (
      <EmptyState
        title="No historical agent snapshots"
        copy="This test has not produced Batch 1 agent telemetry yet. New executions preserve the exact runtime configuration used by each model-backed role."
      />
    );
  }

  return (
    <section aria-labelledby="agents-heading">
      <div className="section-heading">
        <div>
          <h2 id="agents-heading">Agents</h2>
          <p className="muted">
            Historical runtime truth: prompts, tools, model configuration, and model usage captured for this test.
          </p>
        </div>
        <span className="muted">{agents.length} snapshots</span>
      </div>

      <div className="agent-inspector">
        <aside className="agent-list" aria-label="Agent snapshots">
          {agents.map((agent) => (
            <button
              key={agent.id}
              type="button"
              className={"agent-list-item " + (agent.id === selectedId ? "active" : "")}
              onClick={() => setParams({ agent: agent.id }, { replace: true })}
            >
              <span className="agent-list-icon" aria-hidden="true">
                <Bot size={17} />
              </span>
              <span>
                <strong>{agent.persona_name || roleLabel(agent.role)}</strong>
                <small>
                  {agent.mission_name || roleLabel(agent.role)} · {agent.model_name || "model not recorded"}
                </small>
              </span>
            </button>
          ))}
        </aside>

        <div className="agent-detail">
          {detailQuery.isPending ? (
            <LoadingPanel label="Loading agent details" />
          ) : detailQuery.isError ? (
            <ErrorPanel message={detailQuery.error.message} />
          ) : detailQuery.data ? (
            <>
              <header className="agent-detail-header">
                <div>
                  <span className="section-label">{roleLabel(detailQuery.data.role)}</span>
                  <h3>{detailQuery.data.persona_name || detailQuery.data.name}</h3>
                  <p className="muted">
                    {detailQuery.data.mission_name || "Run-level system agent"} · captured {formatDate(detailQuery.data.created_at)}
                  </p>
                </div>
                <span className="monospace">v{detailQuery.data.agent_version}</span>
              </header>

              <dl className="agent-metrics">
                <div>
                  <dt><Gauge size={15} aria-hidden="true" /> Model calls</dt>
                  <dd>{formatNumber(detailQuery.data.usage.attempts)}</dd>
                </div>
                <div>
                  <dt><Cpu size={15} aria-hidden="true" /> Input tokens</dt>
                  <dd>{formatNumber(detailQuery.data.usage.input_tokens)}</dd>
                </div>
                <div>
                  <dt>Output tokens</dt>
                  <dd>{formatNumber(detailQuery.data.usage.output_tokens)}</dd>
                </div>
                <div>
                  <dt>Cached input</dt>
                  <dd>{formatNumber(detailQuery.data.usage.cached_input_tokens)}</dd>
                </div>
              </dl>

              <section className="agent-section">
                <h4>Runtime</h4>
                <dl className="definition-list">
                  <div><dt>Framework</dt><dd>{detailQuery.data.runtime}</dd></div>
                  <div><dt>Model</dt><dd>{detailQuery.data.model_name || "Not recorded"}</dd></div>
                  <div><dt>Template</dt><dd>{detailQuery.data.template_id || "Not applicable"} {detailQuery.data.template_version || ""}</dd></div>
                  <div><dt>Snapshot hash</dt><dd className="monospace">{detailQuery.data.snapshot_sha256}</dd></div>
                </dl>
              </section>

              {detailQuery.data.tools.length > 0 ? (
                <section className="agent-section">
                  <h4>Tools</h4>
                  <div className="agent-chip-list">
                    {detailQuery.data.tools.map((tool) => <code key={tool}>{tool}</code>)}
                  </div>
                </section>
              ) : null}

              <section className="agent-section">
                <h4>Effective prompt</h4>
                <pre className="agent-code">{detailQuery.data.effective_instruction || "No model instruction recorded."}</pre>
              </section>

              {detailQuery.data.runtime_prompt ? (
                <section className="agent-section">
                  <h4>Initial runtime prompt</h4>
                  <pre className="agent-code">{detailQuery.data.runtime_prompt}</pre>
                </section>
              ) : null}

              <section className="agent-section">
                <h4><Braces size={16} aria-hidden="true" /> Runtime YAML</h4>
                <p className="muted">
                  Rendered from the immutable historical snapshot, not from the current source template.
                </p>
                <pre className="agent-code">{detailQuery.data.yaml}</pre>
              </section>

              <section className="agent-section">
                <h4>Model invocations</h4>
                {detailQuery.data.invocations.length ? (
                  <div className="agent-invocation-table">
                    <div className="agent-invocation-header">
                      <span>Status</span><span>Input</span><span>Output</span><span>Latency</span>
                    </div>
                    {detailQuery.data.invocations.map((item) => (
                      <div key={item.id} className="agent-invocation-row">
                        <span>{item.status}</span>
                        <span>{item.input_tokens === null ? "—" : formatNumber(item.input_tokens)}</span>
                        <span>{item.output_tokens === null ? "—" : formatNumber(item.output_tokens)}</span>
                        <span>{item.latency_ms === null ? "—" : formatNumber(item.latency_ms) + " ms"}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted">No model invocations were recorded for this snapshot.</p>
                )}
              </section>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}

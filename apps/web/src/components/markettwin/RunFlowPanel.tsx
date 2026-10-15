import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { request, type TestRunStatus } from "../../lib/api";
import { terminalTestStatuses } from "../../lib/results";
import { StatusBadge } from "../ui/StatusBadge";

export interface RunFlow {
  nodes: { id: string; kind: string; label: string; status: string }[];
  edges: { source: string; target: string }[];
  execution_policy: string;
  revision: string;
}

function FlowStep({ node, connected }: { node: RunFlow["nodes"][number]; connected: boolean }) {
  return <li className={connected ? "run-flow-node connected" : "run-flow-node"}>
    <span className="run-flow-node-label">{node.label}</span>
    <StatusBadge status={node.status} />
    {node.kind === "journey" ? <span className="run-flow-tools">Browser tools · Playwright</span> : null}
  </li>;
}

export function RunFlowPanel({ runId, userId, runStatus, reportReady }: {
  runId: string; userId: string; runStatus: TestRunStatus; reportReady: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [journeysExpanded, setJourneysExpanded] = useState(false);
  const flow = useQuery({
    queryKey: ["run-flow", userId, runId, runStatus, reportReady],
    queryFn: ({ signal }) => request<RunFlow>(`/api/v1/test-runs/${runId}/flow`, { signal }),
    refetchInterval: (runStatus !== "draft" && !terminalTestStatuses.has(runStatus)) || (runStatus === "completed" && !reportReady) ? 5_000 : false,
  });
  const journeyNodes = flow.data?.nodes.filter((node) => node.kind === "journey") ?? [];
  const journeyCount = journeyNodes.length;
  const isFeaturePlan = flow.data?.nodes.some((node) => node.kind === "meta" && node.label === "Feature plan") ?? false;

  return (
    <aside className="run-flow" aria-label={isFeaturePlan ? "Feature execution" : "Agent flow"}>
      <details open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}>
        <summary><span>{isFeaturePlan ? "Feature execution" : "Agent flow"}</span>{flow.data ? <span className="run-flow-count">{journeyCount} {isFeaturePlan ? "cases" : journeyCount === 1 ? "journey" : "journeys"}</span> : null}</summary>
        <div className="run-flow-body">
          {flow.isPending ? <p className="muted" role="status">Loading agent flow…</p> : flow.isError ? (
            <div><p className="error-text" role="alert">Could not load agent flow: {flow.error.message}</p><button type="button" className="text-link" onClick={() => void flow.refetch()}>Try again</button></div>
          ) : flow.data ? (
            <>
              {isFeaturePlan ? <p className="run-flow-caption">Each planned feature case runs once. Recorded results are evaluated after execution.</p> : flow.data.execution_policy === "once_per_journey" ? <p className="run-flow-caption">Each planned journey runs once. The supervisor collects outputs before evaluation.</p> : null}
              <ol className="run-flow-nodes">
                {flow.data.nodes.map((node, index) => {
                  const previous = flow.data.nodes[index - 1];
                  const connected = Boolean(previous && flow.data.edges.some((edge) => edge.source === previous.id && edge.target === node.id));
                  if (node.kind !== "journey") return <FlowStep key={node.id} node={node} connected={connected} />;
                  if (node.id !== journeyNodes[0].id) return null;
                  return <li key="journey-agents" className={connected ? "run-flow-node connected" : "run-flow-node"}>
                    <details className="run-flow-journeys" open={journeysExpanded} onToggle={(event) => setJourneysExpanded(event.currentTarget.open)}>
                      <summary>{isFeaturePlan ? "Feature cases" : "Sequential Agent"} <span className="muted">· {journeyCount} {isFeaturePlan ? "cases" : "subagents"}</span></summary>
                      <ol className="run-flow-nodes">{journeyNodes.map((journey, journeyIndex) => <FlowStep key={journey.id} node={journey} connected={Boolean(journeyIndex && flow.data.edges.some((edge) => edge.source === journeyNodes[journeyIndex - 1].id && edge.target === journey.id))} />)}</ol>
                    </details>
                  </li>;
                })}
              </ol>
              {!flow.data.nodes.length ? <p className="muted">No agent flow has been recorded yet.</p> : null}
            </>
          ) : null}
        </div>
      </details>
    </aside>
  );
}

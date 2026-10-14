import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { request } from "../../lib/api";
import { RunContext } from "../../layouts/RunLayout";
import { ResultsBoundary } from "../../components/markettwin/ResultsBoundary";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { RunAssessmentView } from "../../components/markettwin/RunAssessmentView";

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function RunEvaluationPage() {
  const { run, results, user } = useOutletContext<RunContext>();
  const agents = useQuery({
    queryKey: ["evaluation-agents", user.id, run.id],
    queryFn: ({ signal }) => request<{ id: string; agent_role: string; model_name: string | null; created_at: string; effective_instruction: string | null }[]>(`/api/v1/test-runs/${run.id}/evaluation-agents`, { signal }),
    enabled: results.status === "ready",
  });
  const payload = results.status === "ready" ? results.data.report.payload : {};
  const recorded = Array.isArray(payload.evaluation_records);
  const records = recorded ? (payload.evaluation_records as unknown[]).map(object) : [];
  return (
    <ResultsBoundary>
      <section aria-labelledby="evaluation-heading">
        <div className="section-heading"><div><h2 id="evaluation-heading">Evaluation records</h2><p className="muted">Evaluation follows supervisor collection. These records show the checks performed and the evidence used.</p></div><Link className="text-link" to={`/runs/${run.id}/findings`}>View findings</Link></div>
        <div className="panel run-record">
          <h3>Execution and outcome checks</h3>
          <p>The evaluator checks journey execution failures, unmet criteria and recorded friction. Findings and the report contain its conclusions.</p>
          <Link className="text-link" to={`/runs/${run.id}/journeys`}>Inspect journey outputs</Link>
        </div>
        <RunAssessmentView assessment={payload.assessment} runId={run.id} />
        {agents.data?.length ? <details className="run-assessment-details"><summary>Evaluation agents · {agents.data.length}</summary>{agents.data.map((agent) => <div className="panel run-record" key={agent.id}>
          <h4>{agent.agent_role === "visual_verifier" ? "Visual evidence verifier" : "Testing goal evaluator"}</h4>
          <p className="muted">{agent.model_name || "Model not recorded"} · Created {new Date(agent.created_at).toLocaleString()}</p>
          <p>{agent.agent_role === "visual_verifier" ? "Checks screenshots captured during test execution. This is separate from knowledge ingestion." : "Assesses individual journeys and the overall testing goal from their saved outputs and evidence."}</p>
          {agent.effective_instruction ? <details><summary>Recorded instructions</summary><pre className="run-evaluator-instruction">{agent.effective_instruction}</pre></details> : null}
        </div>)}</details> : agents.isError ? <p className="error-text" role="alert">Could not load evaluation agents: {agents.error.message}</p> : null}
        <h3 className="evaluation-records-heading">Visual evidence checks</h3>
        {!recorded ? <p className="inline-note">Detailed checks were not recorded for this report version. Its saved findings and report remain available.</p> : !records.length ? <p className="inline-note">No visual criteria were selected for verification in this evaluation. This does not indicate that every criterion passed.</p> : <div className="run-records">{records.map((record, index) => {
          const evidence = object(record.evidence);
          const artifacts = Array.isArray(evidence.artifact_ids) ? evidence.artifact_ids.filter((item): item is string => typeof item === "string") : [];
          const steps = Array.isArray(evidence.step_ids) ? evidence.step_ids.filter((item): item is number => typeof item === "number") : [];
          return <article className="panel run-record" key={index}>
            <div className="section-heading"><h3>{typeof record.criterion === "string" ? record.criterion : "Visual check"}</h3><StatusBadge status={record.status === "satisfied" ? "passed" : record.status === "unsatisfied" ? "failed" : "unverified"} /></div>
            <p>{typeof record.rationale === "string" ? record.rationale : "No rationale was recorded."}</p>
            <p className="muted">Persona reported: {typeof record.reported_status === "string" ? record.reported_status : "not recorded"}</p>
            {Array.isArray(record.observed_details) ? <ul>{record.observed_details.filter((item): item is string => typeof item === "string").map((item, detailIndex) => <li key={detailIndex}>{item}</li>)}</ul> : null}
            {steps.length ? <p className="muted">Evidence steps: {steps.join(", ")}</p> : null}
            <div className="run-evidence-links">{artifacts.map((id) => <Link className="text-link" to={`/runs/${run.id}/evidence/${id}`} key={id}>Evidence {id.slice(0, 8)}</Link>)}</div>
          </article>;
        })}</div>}
      </section>
    </ResultsBoundary>
  );
}

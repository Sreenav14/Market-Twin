import { useQuery } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";
import { RunContext } from "../../layouts/RunLayout";
import { api, request } from "../../lib/api";
import { terminalTestStatuses } from "../../lib/results";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { FeatureCases } from "../../components/markettwin/FeatureCases";

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function RunJourneysPage() {
  const { run, user } = useOutletContext<RunContext>();
  const isDeep = run.configuration_snapshot.execution_mode === "deep_feature_v1";
  const journeys = useQuery({
    queryKey: ["run-journeys", user.id, run.id],
    queryFn: ({ signal }) => api.getRunJourneys(run.id, signal),
    refetchInterval: terminalTestStatuses.has(run.status) ? false : 5_000,
  });
  const collection = useQuery({
    queryKey: ["run-collection", user.id, run.id],
    queryFn: ({ signal }) => request<{ collection: Record<string, unknown> | null; collected_at: string | null }>(`/api/v1/test-runs/${run.id}/collection`, { signal }),
    refetchInterval: terminalTestStatuses.has(run.status) ? false : 5_000,
  });
  return (
    <section aria-labelledby="execution-results-heading">
      {isDeep ? <FeatureCases runId={run.id} userId={user.id} /> : null}
      <div className="section-heading">
        <div><h2 id="execution-results-heading">Journey results</h2><p className="muted">Each planned journey runs once. Execution status and the product outcome are recorded separately.</p></div>
        <Link to={`/runs/${run.id}/evaluation`} className="text-link">View evaluation</Link>
      </div>
      {collection.data?.collection ? <p className="inline-note">{isDeep ? "Case collector recorded" : "Supervisor collected"} {String(collection.data.collection.journey_count ?? collection.data.collection.executed)} {isDeep ? "case" : "journey"} outputs{collection.data.collected_at ? ` · ${new Date(collection.data.collected_at).toLocaleString()}` : ""}. Evaluation uses these saved outputs and their evidence.</p> : collection.isError ? <p className="error-text" role="alert">Could not load recorded collection: {collection.error.message}</p> : null}
      {journeys.isPending ? <LoadingPanel label="Loading journey results" /> : journeys.isError ? <ErrorPanel message={journeys.error.message} action={<Button variant="secondary" onClick={() => void journeys.refetch()}>Try again</Button>} /> : !journeys.data.length ? <EmptyState title="No journeys planned yet" copy={run.status === "draft" ? "Start this test to generate its plan and agents." : "Journeys appear once the planner saves its assignments."} /> : (
        <div className="run-records">
          {journeys.data.map((journey) => (
            <article className="panel run-record" id={`journey-${journey.id}`} key={journey.id}>
              <div className="section-heading">
                <div><h3><Link to={`/runs/${run.id}/journeys/${journey.id}`}>{journey.persona_name} · {journey.mission_title}</Link></h3><p className="muted">Journey {journey.ordinal}{journey.attempt_number ? ` · Attempt ${journey.attempt_number}` : ""} · {journey.step_count} steps · {journey.artifact_count} artifacts</p></div>
                <div className="run-record-badges"><span>Execution <StatusBadge status={journey.execution_status || "not started"} /></span><span>Outcome <StatusBadge status={journey.outcome || "not recorded"} /></span></div>
              </div>
              {typeof journey.result?.summary === "string" ? <p>{journey.result.summary}</p> : null}
              {journey.error_message ? <p className="error-text">{journey.error_message}</p> : null}
              <details><summary>Criteria and recorded observations</summary>
                <h4>Success criteria</h4><ul>{journey.success_criteria.map((criterion, index) => <li key={index}>{criterion}</li>)}</ul>
                {(["report_validation_issues", "actions", "observations", "friction_points", "blockers"] as const).map((field) => {
                  const items = strings(journey.result?.[field]);
                  return items.length ? <div key={field}><h4>{field === "report_validation_issues" ? "Report checks" : field.replaceAll("_", " ")}</h4><ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul></div> : null;
                })}
              </details>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

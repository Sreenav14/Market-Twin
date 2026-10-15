import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { request } from "../../lib/api";
import { ArtifactEvidence } from "../../pages/runs/FindingDetailPage";
import { ErrorPanel, LoadingPanel } from "../ui/StateViews";

interface RecordedAssertion {
  assertion_id: string; expected_value: string | number | boolean;
  observed_value: string | number | boolean | null; status: string;
  step_id: number; artifact_ids: string[]; origin: string;
}
interface FeatureCase {
  case_id: string; title: string; kind: string; verdict: string;
  recorded_verdict?: string | null;
  journey_id: string | null; assertions: RecordedAssertion[]; reason?: string;
}
interface CaseResults {
  available: boolean; evaluation_pending?: boolean;
  coverage: Record<string, number> | null; cases: FeatureCase[];
}

interface HitlSummary {
  executor_mode: string;
  reused_auth_cases: number;
  human_requests: Record<string, number>;
  action_approvals: Record<string, number>;
  role_coverage: { role: string; planned: number; authenticated: number; executed: number;
    passed: number; blocked: number; inconclusive: number; not_run: number }[];
  inventory: { feature_key: string; asserted_cases: number; not_explored: number }[];
}

function AuthenticatedCoverage({ runId, userId }: { runId: string; userId: string }) {
  const query = useQuery({
    queryKey: ["hitl-summary", userId, runId],
    queryFn: ({ signal }) => request<HitlSummary>(`/api/v1/test-runs/${runId}/hitl-summary`, { signal }),
    refetchInterval: 5000,
  });
  if (!query.data) return query.isError ? <p>Human assistance summary is unavailable.</p> : null;
  const summary = query.data;
  return <div className="panel" aria-label="Authenticated coverage">
    <h3>Authentication and human contribution</h3>
    <p>{summary.executor_mode === "deterministic_case_steps" ? "Deterministic case execution" : "Agent journey execution"}.
      Human login and approval decisions are recorded separately from agent test steps.</p>
    <p>{summary.human_requests?.completed ?? 0} verified human handoffs · {summary.reused_auth_cases ?? 0} cases with reused authentication · {summary.action_approvals?.consumed ?? 0} consumed action approvals.</p>
    {summary.role_coverage?.length ? summary.role_coverage.map((row) => <p key={row.role}>
      Role {row.role}: {row.authenticated} authenticated · {row.executed} recorded cases · {row.passed} recorded passes · {row.blocked} blocked · {row.inconclusive} inconclusive · {row.not_run} not run.
    </p>) : <p>No role has been verified for a protected feature case.</p>}
    {summary.inventory?.map((item) => <p key={item.feature_key}>
      Planned feature {item.feature_key}: {item.asserted_cases} cases with recorded assertions · {item.not_explored} cases not explored.
    </p>)}
    <p>These counts describe recorded execution; evaluated verdicts appear below. Authentication does not establish full application coverage. Separate browser contexts still require dedicated test data and a reset contract for server changes.</p>
  </div>;
}

export function FeatureCases({ runId, userId }: { runId: string; userId: string }) {
  const query = useQuery({
    queryKey: ["feature-cases", userId, runId],
    queryFn: ({ signal }) => request<CaseResults>(`/api/v1/test-runs/${runId}/test-cases`, { signal }),
    refetchInterval: (state) => !state.state.data?.available || state.state.data?.evaluation_pending ? 5000 : false,
  });
  if (query.isPending) return <LoadingPanel label="Loading feature cases" />;
  if (query.isError) return <ErrorPanel message={query.error.message} />;
  const { cases, coverage, evaluation_pending: pending, available } = query.data;
  return <section aria-label="Feature case coverage">
    <h2>Feature cases</h2>
    <p>Coverage applies to the planned feature. Inferred expectations do not establish a product defect.</p>
    <AuthenticatedCoverage runId={runId} userId={userId} />
    {!available ? <p>The feature plan has not been saved yet.</p> : null}
    {pending ? <p>Evaluation is pending. Completed verdicts appear after evidence verification.</p> : null}
    {coverage ? <p>{coverage.planned} planned · {coverage.passed} passed · {coverage.failed_assertions} failed assertions · {coverage.blocked} blocked · {coverage.inconclusive} inconclusive · {coverage.not_run} not run</p> : null}
    {cases.map((item) => <article className="panel" key={item.case_id}>
      <h3>{item.title}</h3><p>{pending ? "Awaiting evidence evaluation" : item.verdict.replaceAll("_", " ")} · {item.kind.replaceAll("_", " ")}</p>
      {pending && item.recorded_verdict ? <p>Recorded result awaiting verification: {item.recorded_verdict.replaceAll("_", " ")}. This is not a confirmed defect yet.</p> : null}
      {item.verdict === "not_satisfied" ? <p>Next: open the supporting step and compare the screenshot with the expected value.</p> : null}
      {item.reason ? <p>{item.reason.replaceAll("_", " ")}</p> : null}
      {item.journey_id ? <Link to={`/runs/${runId}/journeys/${item.journey_id}`}>Open recorded steps</Link> : null}
      {item.assertions.map((assertion) => <details key={assertion.assertion_id}>
        <summary>{assertion.assertion_id.replaceAll("_", " ")} · {assertion.status.replaceAll("_", " ")}</summary>
        <p>Expected: {String(assertion.expected_value)}<br />Observed: {assertion.observed_value === null ? "Unavailable" : String(assertion.observed_value)}</p>
        <p>Source: {assertion.origin.replaceAll("_", " ")} · Step {assertion.step_id}</p>
        {item.journey_id ? <Link to={`/runs/${runId}/journeys/${item.journey_id}?step=${assertion.step_id}`}>Open supporting step</Link> : null}
        {assertion.artifact_ids.map((artifactId) => <ArtifactEvidence key={artifactId} runId={runId} artifactId={artifactId} />)}
      </details>)}
    </article>)}
  </section>;
}

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

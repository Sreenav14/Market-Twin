import { useEffect, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { RunContext } from "../../layouts/RunLayout";
import { JourneyDetail, request } from "../../lib/api";
import { findingClassification } from "../../lib/results";
import { assertionObservation, initialJourneyStep, journeyBlocker, journeyIdentity } from "../../lib/journeyPresentation";
import { ArtifactEvidence } from "./FindingDetailPage";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";

export function JourneyDetailPage() {
  const { run, user } = useOutletContext<RunContext>();
  const { journeyId = "" } = useParams();
  const [selected, setSelected] = useState<number | null>(null);
  const [parameters] = useSearchParams();
  const requestedStep = parameters.get("step");
  useEffect(() => {
    const stepId = Number(requestedStep);
    setSelected(Number.isSafeInteger(stepId) && stepId > 0 ? stepId : null);
  }, [requestedStep, journeyId]);
  const query = useInfiniteQuery({
    queryKey: ["journey-detail", user.id, run.id, journeyId], initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => request<JourneyDetail>(
      `/api/v1/test-runs/${run.id}/journeys/${journeyId}?after_step=${pageParam}`, { signal },
    ), getNextPageParam: (page) => page.next_after_step ?? undefined,
  });
  if (query.isPending) return <LoadingPanel label="Loading recorded journey" />;
  if (query.isError) return <ErrorPanel message={query.error.message} action={<Button onClick={() => void query.refetch()}>Try again</Button>} />;
  const pages = query.data.pages;
  const { journey, findings } = pages[0];
  if (pages.some((page) => page.journey.execution_id !== journey.execution_id))
    return <ErrorPanel message="This journey has a new execution attempt. Refresh to view its evidence." action={<Button onClick={() => void query.refetch()}>Refresh journey</Button>} />;
  const steps = pages.flatMap((page) => page.steps);
  const artifacts = pages.flatMap((page) => page.artifacts);
  const step = steps.find((item) => item.id === selected) ?? (selected === null ? initialJourneyStep(steps) : undefined);
  const identity = journeyIdentity(journey, run.configuration_snapshot.execution_mode === "deep_feature_v1");
  const observation = assertionObservation(step?.observation_summary ?? null);
  const blocker = journeyBlocker(journey, step);
  const stepArtifacts = step ? artifacts.filter((item) => item.step_id === step.id) : [];
  const screenshot = stepArtifacts.find((item) => item.kind === "viewport" && item.artifact_type === "screenshot");
  const entries = Array.isArray(journey.result?.criterion_evidence) ? journey.result.criterion_evidence.filter((item): item is { criterion: string; status: string } => typeof item === "object" && item !== null && typeof item.criterion === "string" && typeof item.status === "string") : [];
  return <section>
    <Link className="back-link" to={`/runs/${run.id}/journeys`}>← All journeys</Link>
    <div className="section-heading"><div><h2>{identity.discovery ? "Browser discovery" : journey.mission_title}</h2><p>{identity.discovery ? "Inspect the authorized target before generating test cases; request assistance only if a challenge is encountered." : journey.mission_objective}</p></div><div><StatusBadge status={journey.execution_status ?? "not started"} /> <Button variant="secondary" disabled={query.isFetching} onClick={() => void query.refetch()}>Refresh journey</Button></div></div>
    <p className="muted">Executor: {identity.executor}{identity.caseId ? ` · Case ${identity.caseId}` : ""} · Attempt {journey.attempt_number ?? "not started"}</p>
    <p className="muted">{identity.discovery ? "Discovery is a preparation stage, not a feature case or product verdict." : identity.featureCase ? "The planner selected this case; browser actions and assertions execute deterministically." : journey.persona_perspective}</p>
    {typeof run.target_snapshot.base_url === "string" ? <p><strong>Test target:</strong> {run.target_snapshot.base_url}</p> : null}
    <nav aria-label="Journey investigation"><Link className="text-link" to={`/runs/${run.id}/evidence`}>Browse recorded evidence</Link>{" · "}<Link className="text-link" to={`/runs/${run.id}/human-action`}>Human Assistance history</Link></nav>
    {typeof run.target_snapshot.target_id === "string" ? <p><Link className="text-link" to={`/targets/${run.target_snapshot.target_id}/network`}>Review approved origins and request a new scope</Link></p> : null}
    <p>{journey.summary ?? "No journey summary recorded yet."}</p>
    <p>{identity.discovery ? "Discovery stage" : <>Product outcome: <StatusBadge status={journey.outcome ?? "not recorded"} /></>} · {journey.step_count} recorded steps</p>
    {journey.error_message ? <p className="error-text" role="alert">{journey.error_message}</p> : null}
    {blocker ? <p className="inline-note" role="status">{blocker}</p> : null}
    <div className="journey-evidence-grid"><div><h3>Browser steps</h3>
      <ol className="journey-step-list">{steps.map((item) => <li key={item.id}><button className={`journey-step ${step?.id === item.id ? "selected" : ""}`} data-status={item.status} aria-pressed={step?.id === item.id} onClick={() => setSelected(item.id)}><span>Step {item.step_number} · {item.action_type.replaceAll("_", " ")}</span><strong>{item.action_summary}</strong><StatusBadge status={item.status} /></button></li>)}</ol>
      {!steps.length ? <EmptyState title="No browser steps recorded" copy="A planned journey does not imply that browser execution occurred." /> : null}
      {query.hasNextPage ? <Button variant="secondary" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>{query.isFetchingNextPage ? "Loading…" : "Load more steps"}</Button> : null}
    </div><aside className="panel journey-selected-evidence" aria-label="Selected step evidence">
      <h3>{step ? `Step ${step.step_number} evidence` : "Evidence"}</h3>
      {step ? <><p><strong>What:</strong> {step.action_summary}</p><p><strong>Who:</strong> {identity.executor}</p><p><strong>Why:</strong> {identity.discovery ? "Inspect the authorized page before planning." : journey.mission_objective}</p></> : selected !== null ? <p>This requested step is not in the loaded page. Load more steps to locate it.</p> : null}
      {observation ? <dl><dt>Assertion</dt><dd>{observation.id} · {observation.oracle}</dd><dt>Expected</dt><dd>{observation.expected}</dd><dt>Observed</dt><dd>{observation.observed}</dd><dt>Result</dt><dd><StatusBadge status={observation.status} /></dd>{observation.reason ? <><dt>Reason</dt><dd>{observation.reason}</dd></> : null}</dl> : step?.observation_summary ? <p>{step.observation_summary}</p> : null}
      {screenshot ? <ArtifactEvidence key={screenshot.id} runId={run.id} artifactId={screenshot.id} autoLoad /> : <p>Evidence unavailable for this step.</p>}
      {stepArtifacts.filter((item) => item.id !== screenshot?.id).map((item) => <details key={item.id}><summary>{item.kind?.replaceAll("_", " ") ?? item.artifact_type}</summary><ArtifactEvidence runId={run.id} artifactId={item.id} /></details>)}
      {pages.some((page) => page.artifacts_truncated) ? <p className="inline-note">Artifact metadata exceeded this page's limit. Request fewer steps to inspect the remainder.</p> : null}
    </aside></div>
    <details className="panel"><summary>{identity.discovery ? "Discovery checks" : identity.featureCase ? "Planned assertions" : "Reported criteria"}</summary><p className="muted">{identity.discovery ? "Discovery prepares page context for planning; it does not execute a test case or verify an identity unless a separate policy was configured." : identity.featureCase ? "These expectations belong to the frozen case. Select an assertion step to inspect its recorded result." : "These are the simulated user's reports. Verified findings appear separately below."}</p><ul>{(identity.discovery ? [] : journey.success_criteria).map((criterion) => <li key={criterion}>{criterion}{identity.featureCase ? null : <> <StatusBadge status={entries.find((entry) => entry.criterion === criterion)?.status ?? "not reported"} /></>}</li>)}</ul></details>
    <h3>Linked findings</h3>{findings.length ? findings.map((finding) => <article className="panel" key={finding.id}><p className="section-label">{findingClassification(finding)}</p><Link to={`/runs/${run.id}/findings/${finding.id}`}>{finding.title}</Link><p>{finding.summary}</p></article>) : <p className="muted">No linked findings recorded. This does not establish that the journey passed.</p>}
  </section>;
}

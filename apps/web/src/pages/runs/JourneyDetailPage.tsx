import { useEffect, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { RunContext } from "../../layouts/RunLayout";
import { JourneyDetail, request } from "../../lib/api";
import { findingClassification } from "../../lib/results";
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
  }, [requestedStep]);
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
  const step = steps.find((item) => item.id === selected) ?? (selected === null ? steps[0] : undefined);
  const stepArtifacts = step ? artifacts.filter((item) => item.step_id === step.id) : [];
  const screenshot = stepArtifacts.find((item) => item.kind === "viewport" && item.artifact_type === "screenshot");
  const entries = Array.isArray(journey.result?.criterion_evidence) ? journey.result.criterion_evidence.filter((item): item is { criterion: string; status: string } => typeof item === "object" && item !== null && typeof item.criterion === "string" && typeof item.status === "string") : [];
  return <section>
    <Link className="back-link" to={`/runs/${run.id}/journeys`}>← All journeys</Link>
    <div className="section-heading"><div><h2>{journey.mission_title}</h2><p>{journey.mission_objective}</p></div><div><StatusBadge status={journey.execution_status ?? "not started"} /> <Button variant="secondary" disabled={query.isFetching} onClick={() => void query.refetch()}>Refresh journey</Button></div></div>
    <p className="muted">{journey.persona_name} · {journey.persona_perspective}</p>
    <p>{journey.summary ?? "No journey summary recorded yet."}</p>
    <p>Product outcome: <StatusBadge status={journey.outcome ?? "not recorded"} /> · {journey.step_count} recorded steps</p>
    {journey.error_message ? <p className="error-text" role="alert">{journey.error_message}</p> : null}
    <div className="journey-evidence-grid"><div><h3>Browser steps</h3>
      <ol className="journey-step-list">{steps.map((item) => <li key={item.id}><button className={`journey-step ${step?.id === item.id ? "selected" : ""}`} data-status={item.status} aria-pressed={step?.id === item.id} onClick={() => setSelected(item.id)}><span>Step {item.step_number} · {item.action_type.replaceAll("_", " ")}</span><strong>{item.action_summary}</strong><StatusBadge status={item.status} /></button></li>)}</ol>
      {!steps.length ? <EmptyState title="No browser steps recorded" copy="A planned journey does not imply that browser execution occurred." /> : null}
      {query.hasNextPage ? <Button variant="secondary" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>{query.isFetchingNextPage ? "Loading…" : "Load more steps"}</Button> : null}
    </div><aside className="panel journey-selected-evidence" aria-label="Selected step evidence">
      <h3>{step ? `Step ${step.step_number} evidence` : "Evidence"}</h3>
      {step?.observation_summary ? <p className="monospace">{step.observation_summary}</p> : null}
      {screenshot ? <ArtifactEvidence key={screenshot.id} runId={run.id} artifactId={screenshot.id} autoLoad /> : <p>Evidence unavailable for this step.</p>}
      {stepArtifacts.filter((item) => item.id !== screenshot?.id).map((item) => <details key={item.id}><summary>{item.kind?.replaceAll("_", " ") ?? item.artifact_type}</summary><ArtifactEvidence runId={run.id} artifactId={item.id} /></details>)}
      {pages.some((page) => page.artifacts_truncated) ? <p className="inline-note">Artifact metadata exceeded this page's limit. Request fewer steps to inspect the remainder.</p> : null}
    </aside></div>
    <details className="panel"><summary>Reported criteria</summary><p className="muted">These are the simulated user's reports. Verified findings appear separately below.</p><ul>{journey.success_criteria.map((criterion) => <li key={criterion}>{criterion} <StatusBadge status={entries.find((entry) => entry.criterion === criterion)?.status ?? "not reported"} /></li>)}</ul></details>
    <h3>Linked findings</h3>{findings.length ? findings.map((finding) => <article className="panel" key={finding.id}><p className="section-label">{findingClassification(finding)}</p><Link to={`/runs/${run.id}/findings/${finding.id}`}>{finding.title}</Link><p>{finding.summary}</p></article>) : <p className="muted">No linked findings recorded. This does not establish that the journey passed.</p>}
  </section>;
}

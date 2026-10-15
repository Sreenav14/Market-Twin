import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { RunContext } from "../../layouts/RunLayout";
import { api, request, type JourneyDetail } from "../../lib/api";
import { ArtifactEvidence } from "./FindingDetailPage";

export function RunEvidencePage() {
  const { run, user } = useOutletContext<RunContext>();
  const [journeyId, setJourneyId] = useState("");
  const journeys = useQuery({
    queryKey: ["run-journeys", user.id, run.id],
    queryFn: ({ signal }) => api.getRunJourneys(run.id, signal),
  });
  const selectedJourneyId = journeyId || journeys.data?.[0]?.id || "";
  const evidence = useQuery({
    queryKey: ["evidence-index", user.id, run.id, selectedJourneyId],
    enabled: Boolean(selectedJourneyId),
    queryFn: ({ signal }) => request<JourneyDetail>(
      `/api/v1/test-runs/${run.id}/journeys/${selectedJourneyId}?after_step=0`, { signal },
    ),
  });
  if (journeys.isPending) return <LoadingPanel label="Loading recorded evidence" />;
  if (journeys.isError) return <ErrorPanel message={journeys.error.message} action={<Button variant="secondary" onClick={() => void journeys.refetch()}>Try again</Button>} />;
  return (
    <section className="evidence-workbench" aria-labelledby="evidence-heading">
      <div className="section-heading"><div><h2 id="evidence-heading">Recorded evidence</h2><p className="muted">Artifacts are requested through the authenticated access endpoint and loaded only when selected.</p></div>
        {journeys.data.length ? <label className="filter-select">Journey<select aria-label="Select journey evidence" value={selectedJourneyId} onChange={(event) => setJourneyId(event.target.value)}>{journeys.data.map((journey) => <option value={journey.id} key={journey.id}>{journey.persona_name} · {journey.mission_title}</option>)}</select></label> : null}
      </div>
      {!journeys.data.length ? <p className="inline-note">No recorded journeys are available for this test. Planned work does not imply that evidence was captured.</p> : null}
      {evidence.isPending && selectedJourneyId ? <LoadingPanel label="Loading evidence metadata" /> : null}
      {evidence.isError ? <ErrorPanel message={evidence.error.message} action={<Button variant="secondary" onClick={() => void evidence.refetch()}>Try again</Button>} /> : null}
      {evidence.data ? <>
        <p className="muted">{evidence.data.artifacts.length} artifacts in this page · {evidence.data.journey.step_count} recorded steps</p>
        {evidence.data.artifacts.length ? <ul className="evidence-artifact-list">{evidence.data.artifacts.map((artifact) => <li key={artifact.id}>
          <article className="panel evidence-artifact">
            <div><strong>{artifact.artifact_type.replaceAll("_", " ")}</strong><p className="muted">Artifact <code>{artifact.id}</code> · {artifact.kind?.replaceAll("_", " ") ?? "type not recorded"}{artifact.step_id ? ` · Step ${artifact.step_id}` : " · No step linked"} · {new Date(artifact.created_at).toLocaleString()}</p></div>
            <ArtifactEvidence runId={run.id} artifactId={artifact.id} />
          </article>
        </li>)}</ul> : <p className="inline-note">No artifact metadata is available for this journey page.</p>}
        {evidence.data.artifacts_truncated || evidence.data.next_after_step ? <p className="inline-note">This evidence view is bounded to the first recorded page. <Link to={`/runs/${run.id}/journeys/${selectedJourneyId}`}>Open the journey to load more steps and evidence.</Link></p> : null}
        <Link className="text-link" to={`/runs/${run.id}/journeys/${selectedJourneyId}`}>Inspect journey steps and evidence</Link>
      </> : null}
    </section>
  );
}

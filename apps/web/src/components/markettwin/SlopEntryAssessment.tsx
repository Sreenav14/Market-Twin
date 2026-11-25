import { ArtifactEvidence } from "./ArtifactEvidence";

const viewportLabels: Record<string, string> = {
  desktop1280: "Desktop (1280 px)",
  mobile320: "Mobile (320 px)",
};

type EntryAssessment = {
  url: string;
  viewports: string[];
  elements_judged: number;
  findings_count: number;
  findings: Array<{
    detail: string;
    element?: string;
    severity: string;
    viewports: string[];
    artifact_ids: string[];
  }>;
};

export function SlopEntryAssessment({ runId, snapshot }: {
  runId: string;
  snapshot: Record<string, unknown>;
}) {
  const assessment = snapshot.slop_entry_assessment as EntryAssessment | undefined;
  if (!assessment) return null;
  const labels = (viewports: string[]) => viewports.map(viewport => viewportLabels[viewport] ?? viewport).join(" · ");
  return (
    <section className="panel section-block" aria-label="Submitted page assessment">
      <h2>Submitted page assessment</h2>
      <p style={{ overflowWrap: "anywhere" }}>{assessment.url}</p>
      <p>{labels(assessment.viewports)} · {assessment.elements_judged} visual elements assessed across these views.</p>
      {assessment.findings.length > 0 ? <ul>
        {assessment.findings.map(finding => (
          <li key={JSON.stringify([finding.detail, finding.element])}>
            {finding.severity === "review" ? <strong>Design observation. </strong> : null}
            {finding.detail}{finding.element ? <> · {finding.element}</> : null}
            {finding.viewports.length ? <p>{labels(finding.viewports)}</p> : null}
            {finding.artifact_ids.map(id => <ArtifactEvidence key={id} runId={runId} artifactId={id} />)}
          </li>
        ))}
      </ul> : <p>{assessment.elements_judged > 0
        ? "The initial visual checks found no issues to report in these views."
        : "These views yielded too little evidence for an element assessment."}</p>}
      {assessment.findings_count > assessment.findings.length &&
        <p>Showing {assessment.findings.length} of {assessment.findings_count} observations from the initial views.</p>}
      <p>This assessment covers the initial page views. Interaction states and site-wide checks are covered separately in the full report.</p>
    </section>
  );
}

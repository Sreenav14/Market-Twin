import { Link, useOutletContext, useParams } from "react-router-dom";
import { RunContext } from "../../layouts/RunLayout";
import { ArtifactEvidence } from "./FindingDetailPage";
export function EvidenceDetailPage() {
  const { run } = useOutletContext<RunContext>();
  const { artifactId = "" } = useParams();
  return (
    <section className="panel run-record" aria-labelledby="evidence-heading">
      <h2 id="evidence-heading">Recorded evidence</h2>
      <p className="muted">Artifact {artifactId}. Access is checked against this test before a temporary preview is provided.</p>
      <ArtifactEvidence key={artifactId} runId={run.id} artifactId={artifactId} />
      <Link className="text-link" to={`/runs/${run.id}/evaluation`}>Back to evaluation</Link>
    </section>
  );
}

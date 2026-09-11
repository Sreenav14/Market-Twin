import { Link, useOutletContext, useParams } from "react-router-dom";
import { ArrowLeft, Paperclip, Route, ScanSearch } from "lucide-react";
import { RunContext } from "../../layouts/RunLayout";
import { ResultsBoundary } from "../../components/markettwin/ResultsBoundary";
import { CopyButton } from "../../components/markettwin/CopyButton";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { EmptyState } from "../../components/ui/StateViews";
import { reportMetrics } from "../../lib/results";

export function FindingDetailPage() {
  const { run, results } = useOutletContext<RunContext>();
  const { findingId } = useParams();
  const finding = results.status === "ready" ? results.data.findings.find(item => item.id === findingId) : undefined;
  return <ResultsBoundary>{finding ? <>
    <Link className="back-link" to={`/runs/${run.id}/findings`}><ArrowLeft size={15} aria-hidden="true" />All findings</Link>
    <div className="finding-detail-grid"><article className="finding-article"><div className="finding-title-meta"><StatusBadge status={finding.severity} /><span className="category-label">{finding.category.replaceAll("_", " ")}</span></div><h2>{finding.title}</h2><p className="reading-lead">{finding.summary}</p>
      <section><h3>Recommendation</h3><p>{finding.recommendation || "No recommendation was included in this evaluation."}</p>{finding.recommendation ? <CopyButton text={finding.recommendation} label="Copy recommendation" /> : null}</section>
      <section><h3><Paperclip size={18} aria-hidden="true" />Supporting references</h3><p className="muted">These references link this finding to recorded steps and artifacts. Artifact contents are not available in this view yet.</p>
        {finding.evidence.step_ids.length + finding.evidence.artifact_ids.length === 0 ? <p className="inline-note">No evidence references were attached. Treat this finding as requiring further investigation.</p> : <ul className="reference-list">{finding.evidence.step_ids.map(id => <li key={`step-${id}`}><ScanSearch size={16} aria-hidden="true" /><span>Execution step <code>{id}</code></span></li>)}{finding.evidence.artifact_ids.map(id => <li key={id}><Paperclip size={16} aria-hidden="true" /><span>Artifact <code>{id}</code></span><CopyButton text={id} label="Copy artifact ID" /></li>)}</ul>}
      </section>
      <section><h3><Route size={18} aria-hidden="true" />Affected journeys</h3><p className="muted">Journey identifiers connect this finding to its evaluation context. Detailed playback is not available here yet.</p><ul className="reference-list">{finding.journey_ids.map(id => <li key={id}><code>{id}</code><CopyButton text={id} label="Copy journey ID" /></li>)}</ul>{finding.journey_ids.length === 0 ? <p>No journey links were included.</p> : null}</section>
    </article><aside className="provenance-panel"><p className="section-label">Finding provenance</p><dl><div><dt>Evaluation</dt><dd>{results.status === "ready" && reportMetrics(results.data).deterministic ? "Deterministic checks" : "Recorded evaluation"}</dd></div><div><dt>Status</dt><dd><StatusBadge status={finding.status} /></dd></div><div><dt>Report version</dt><dd>{results.status === "ready" ? results.data.report.version : "—"}</dd></div><div><dt>Finding ID</dt><dd className="monospace">{finding.id}</dd></div></dl><p>Execution records describe what happened. A simulated user’s conclusions describe how the experience was interpreted.</p></aside></div>
  </> : <EmptyState title="Finding not found" copy="This finding is not part of the current report. Return to the findings list to choose another." action={<Link className="secondary-button" to={`/runs/${run.id}/findings`}>All findings</Link>} />}</ResultsBoundary>;
}

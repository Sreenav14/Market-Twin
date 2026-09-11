import { Link, useOutletContext } from "react-router-dom";
import { Check, FileText, ArrowUpRight } from "lucide-react";
import { RunContext } from "../../layouts/RunLayout";
import { ResultsBoundary } from "../../components/markettwin/ResultsBoundary";
import { FindingListItem } from "../../components/markettwin/FindingListItem";
import { CopyButton } from "../../components/markettwin/CopyButton";
import { reportMetrics, sortFindings } from "../../lib/results";
import { textValue } from "../../lib/format";

export function RunOverviewPage() {
  const { run, results } = useOutletContext<RunContext>();
  const ready = results.status === "ready";
  const stages = ["Created", "Planning", "Execution", "Evaluation"];
  const stage = ready ? 4 : run.status === "completed" ? 3 : ["running", "queued", "evaluating"].includes(run.status) ? 2 : run.status === "planning" ? 1 : 0;
  const stopped = ["failed", "cancelled", "timed_out", "policy_blocked"].includes(run.status);
  const metrics = ready ? reportMetrics(results.data) : null;
  return <>
    <ol className="lifecycle-rail" aria-label="Test lifecycle">{stages.map((label, index) => <li key={label} className={stopped ? "stage-stopped" : index < stage ? "stage-done" : index === stage ? "stage-current" : ""}>
      <span className="stage-marker" aria-hidden="true">{!stopped && index < stage ? <Check size={13} /> : index + 1}</span><span>{label}<small>{stopped ? index === 0 ? "Test ended" : "Not confirmed" : index < stage ? "Complete" : index === stage ? "Current stage" : "Up next"}</small></span>
    </li>)}</ol>
    <ResultsBoundary>{ready && metrics ? <>
      <div className="study-summary">
        <div className="summary-reading"><p className="section-label">The test at a glance</p><h2>{results.data.findings.length === 0 ? "No findings in this evaluation" : `${results.data.findings.length} ${results.data.findings.length === 1 ? "finding" : "findings"} to review`}</h2><p>{results.data.report.executive_summary || "Open the findings to inspect the evaluation and its supporting references."}</p><Link className="text-link inline-link" to={`/runs/${run.id}/report`}>Read the full report <ArrowUpRight size={16} aria-hidden="true" /></Link></div>
        <dl className="result-metrics"><div><dt>Journeys evaluated</dt><dd>{metrics.journeyTotal ?? "—"}</dd></div><div><dt>High priority findings</dt><dd>{metrics.criticalCount}</dd></div><div><dt>Linked artifacts</dt><dd>{metrics.artifactCount}</dd></div></dl>
      </div>
      {results.data.findings.length > 0 ? <section className="section-block"><div className="section-heading"><h2>Start with these findings</h2><Link className="text-link" to={`/runs/${run.id}/findings`}>View all findings</Link></div><ul className="finding-list">{sortFindings(results.data.findings).slice(0, 3).map(finding => <FindingListItem key={finding.id} finding={finding} runId={run.id} />)}</ul></section> : <p className="inline-note">No findings does not guarantee a problem-free experience. Review the report’s scope and journey outcomes.</p>}
      <div className="provenance-note"><FileText size={16} aria-hidden="true" /><span>{metrics.deterministic ? "Deterministic evaluation" : "Evaluation report"} · Report version {results.data.report.version}. References identify the evidence linked to each finding.</span></div>
    </> : null}</ResultsBoundary>
    <details className="study-details"><summary>Test configuration</summary><dl className="definition-list"><div><dt>Target</dt><dd>{textValue(run.target_snapshot.name, "Target")}</dd></div><div><dt>Environment</dt><dd>{textValue(run.target_snapshot.environment)}</dd></div><div><dt>Authentication</dt><dd>{run.target_snapshot.requires_auth ? "Protected target" : "Public target"}</dd></div><div><dt>Test identifier</dt><dd><span className="monospace">{run.id}</span> <CopyButton text={run.id} label="Copy ID" /></dd></div></dl></details>
  </>;
}

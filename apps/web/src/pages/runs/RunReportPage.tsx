import { Link, useOutletContext } from "react-router-dom";
import { FileText, ArrowUpRight } from "lucide-react";
import { RunContext } from "../../layouts/RunLayout";
import { ResultsBoundary } from "../../components/markettwin/ResultsBoundary";
import { CopyButton } from "../../components/markettwin/CopyButton";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { formatDate, reportMetrics, severityOrder, sortFindings } from "../../lib/results";

export function RunReportPage() {
  const { run, results } = useOutletContext<RunContext>();
  const data = results.status === "ready" ? results.data : null;
  const metrics = data ? reportMetrics(data) : null;
  return <ResultsBoundary>{data && metrics ? <div className="report-layout">
    <nav className="report-toc" aria-label="Report contents"><span className="section-label">In this report</span><a href="#report-summary">Executive summary</a><a href="#report-outcomes">Journey outcomes</a><a href="#report-findings">Findings</a><a href="#report-scope">Scope & provenance</a></nav>
    <article className="report-document"><header className="report-header"><div className="report-label"><FileText size={18} aria-hidden="true" />Test report <span>Version {data.report.version}</span></div><h2>What this test found</h2><p className="muted">Generated {formatDate(data.report.generated_at)}</p>{data.report.executive_summary ? <CopyButton text={data.report.executive_summary} label="Copy summary" /> : null}</header>
      <section id="report-summary"><h3>Executive summary</h3><p className="reading-lead">{data.report.executive_summary || "No executive summary was included in this report."}</p></section>
      <section id="report-outcomes"><h3>Journey outcomes</h3><p>{metrics.journeyTotal === null ? "The total number of evaluated journeys was not included." : `${metrics.journeyTotal} journeys were included in this evaluation.`} Execution completion and product outcomes are separate measures.</p>
        {metrics.outcomes.length > 0 ? <dl className="outcome-list">{metrics.outcomes.map(([outcome, count]) => <div key={outcome}><dt><StatusBadge status={outcome === "none" ? "not reported" : outcome} /></dt><dd>{count}</dd></div>)}</dl> : <p className="muted">Outcome counts are not available.</p>}
      </section>
      <section id="report-findings"><h3>Findings</h3><div className="severity-summary">{severityOrder.map(severity => { const count = data.findings.filter(finding => finding.severity === severity).length; return <span key={severity}><StatusBadge status={severity} /><strong>{count}</strong></span>; })}</div>
        {data.findings.length === 0 ? <p>No findings were produced by the available checks. This is not a guarantee that the product has no usability problems.</p> : sortFindings(data.findings).map(finding => <section className="report-finding" key={finding.id}><div><StatusBadge status={finding.severity} /><span className="category-label">{finding.category.replaceAll("_", " ")}</span></div><h4><Link to={`/runs/${run.id}/findings/${finding.id}`}>{finding.title}<ArrowUpRight size={16} aria-hidden="true" /></Link></h4><p>{finding.summary}</p>{finding.recommendation ? <p><strong>Recommendation: </strong>{finding.recommendation}</p> : null}</section>)}
      </section>
      <section id="report-scope"><h3>Scope & provenance</h3><p>{metrics.deterministic ? "This report was generated from deterministic evaluation checks." : "This report contains the evaluation recorded for this test."} It summarizes the available journeys and findings, with linked references preserved in each finding.</p><p>Simulated user conclusions are not a replacement for research with real customers. Validate important product decisions against the underlying evidence and representative users.</p><dl className="definition-list"><div><dt>Report ID</dt><dd className="monospace">{data.report.id}</dd></div><div><dt>Test ID</dt><dd className="monospace">{run.id}</dd></div></dl></section>
    </article></div> : null}</ResultsBoundary>;
}

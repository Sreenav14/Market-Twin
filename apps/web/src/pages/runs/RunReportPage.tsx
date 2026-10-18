import { Link, useOutletContext } from "react-router-dom";
import { FileText, ArrowUpRight } from "lucide-react";
import type { Finding } from "../../lib/api";
import { RunContext } from "../../layouts/RunLayout";
import { ResultsBoundary } from "../../components/markettwin/ResultsBoundary";
import { CopyButton } from "../../components/markettwin/CopyButton";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { RunAssessmentView } from "../../components/markettwin/RunAssessmentView";
import { FeatureCases } from "../../components/markettwin/FeatureCases";
import {
  formatDate,
  findingClassification,
  isConfirmedFinding,
  reportMetrics,
  severityOrder,
  sortFindings,
} from "../../lib/results";

function diagnosticGroup(finding: Finding): string {
  if (finding.category === "policy") return "Scope and safety restrictions";
  if (finding.category === "execution_reliability" && finding.title.startsWith("Journey timed out:"))
    return "Execution timeouts";
  return finding.title;
}

function ReportFinding({ finding, runId }: { finding: Finding; runId: string }) {
  return <li className="ledger-finding">
    <div className="ledger-finding-meta"><StatusBadge status={finding.severity}/><span>{findingClassification(finding)}</span></div>
    <h4><Link to={"/runs/" + runId + "/findings/" + finding.id}>{finding.title} <ArrowUpRight size={14} aria-hidden="true" /></Link></h4>
    <p>{finding.summary}</p>
    {finding.recommendation ? <p className="ledger-next"><strong>Next step: </strong>{finding.recommendation}</p> : null}
    <Link className="ledger-evidence-link" to={"/runs/" + runId + "/findings/" + finding.id}>
      {finding.evidence.step_ids.length || finding.evidence.artifact_ids.length
        ? "Inspect supporting evidence" : "Inspect recorded details and limitations"}
    </Link>
  </li>;
}

export function RunReportPage() {
  const { run, results, user } = useOutletContext<RunContext>();
  const data = results.status === "ready" ? results.data : null;
  const metrics = data ? reportMetrics(data) : null;
  const featureRun = data?.report.payload.mode === "deep_feature_v1" || run.configuration_snapshot.execution_mode === "deep_feature_v1";
  const findings = data?.findings ?? [];
  const verified = sortFindings(findings.filter(isConfirmedFinding));
  const reliability = findings.filter((finding) => findingClassification(finding) === "Test execution issue");
  const observations = sortFindings(findings.filter((finding) =>
    !isConfirmedFinding(finding) && findingClassification(finding) !== "Test execution issue"));
  const groups = new Map<string, Finding[]>();
  for (const finding of reliability) {
    const title = diagnosticGroup(finding);
    groups.set(title, [...(groups.get(title) ?? []), finding]);
  }
  const completed = metrics?.statuses.find(([status]) => status === "completed")?.[1] ?? 0;
  const journeyTotal = metrics?.journeyTotal ?? null;
  const limited = journeyTotal === null || completed < journeyTotal;
  const conclusion = verified.length
    ? String(verified.length) + " evidence-linked product issue(s) need review."
    : limited ? "No product defects were verified. Test coverage was incomplete."
      : "No product defects were verified in this completed test scope.";
  return (
    <ResultsBoundary>
      {data && metrics ? (
        <div className="report-layout evidence-ledger">
          <nav className="report-toc ledger-toc" aria-label="Sections in this report">
            <span className="section-label">In this report</span>
            <a href="#report-summary">At a glance</a>
            <a href="#report-findings">Verified findings</a>
            <a href="#report-observations">Needs verification</a>
            <a href="#report-reliability">Test reliability</a>
            <a href="#report-outcomes">Coverage</a>
            <a href="#report-assessment">Assessment</a>
            <a href="#report-scope">Source &amp; scope</a>
          </nav>
          <article className="report-document ledger-paper">
            <header className="ledger-hero" id="report-summary">
              <div className="ledger-topline">
                <span className="ledger-eyebrow"><FileText size={14} aria-hidden="true"/> MarketTwin / Test report v{data.report.version}</span>
                <span className={limited ? "ledger-health ledger-health-limited" : "ledger-health"}>
                  {limited ? "Limited coverage" : "Execution completed"}
                </span>
              </div>
              <h2>What the evidence <em>actually says.</em></h2>
              <p className="ledger-lead">{conclusion}</p>
              <p className="ledger-support">Product outcomes, unverified observations and execution problems are separate.
                A lack of verified defects does not establish a defect-free application.</p>
              <div className="ledger-actions">
                {data.report.executive_summary ? <CopyButton text={data.report.executive_summary} label="Copy recorded summary"/> : null}
                <a href="#report-findings">Review findings <ArrowUpRight size={14} aria-hidden="true"/></a>
                <time dateTime={data.report.generated_at}>Generated {formatDate(data.report.generated_at)}</time>
              </div>
            </header>
            <dl className="ledger-metrics">
              <div><dt>01 / Verified product issues</dt><dd>{verified.length}</dd><small>Evidence-linked only</small></div>
              <div><dt>02 / Normal completion</dt><dd>{journeyTotal === null ? "Unknown" : <>{completed}<span> / {journeyTotal}</span></>}</dd><small>Completion is not a pass</small></div>
              <div><dt>03 / Execution diagnostics</dt><dd>{reliability.length}</dd><small>Technical or policy limitations</small></div>
            </dl>
            <div className="ledger-columns">
              <div className="ledger-main">
                <section id="report-findings" className="ledger-section">
                  <span className="ledger-kicker">01 / Verified evidence</span>
                  <h3>Product findings</h3>
                  {verified.length ? <>
                    <p>Each confirmed finding is linked to the evidence required by MarketTwin's verification contract.</p>
                    <ul className="ledger-findings">{verified.map((f) => <ReportFinding key={f.id} finding={f} runId={run.id}/>)}</ul>
                    <div className="ledger-severity" aria-label="Verified product issue severities">
                      {severityOrder.map((severity) => {
                        const count = verified.filter((f) => f.severity === severity).length;
                        return count ? <span key={severity}><StatusBadge status={severity}/> {count}</span> : null;
                      })}
                    </div>
                  </> : <div className="ledger-empty">
                    <strong>No product defect could be verified from this run.</strong>
                    <p>{limited
                      ? "Some testing did not finish. Investigate the unverified observations and execution limitations before drawing conclusions."
                      : "The completed scope produced no verified defect finding. Untested states remain outside this conclusion."}</p>
                  </div>}
                </section>
                <section id="report-observations" className="ledger-section">
                  <span className="ledger-kicker">02 / Further investigation</span>
                  <h3>Observations to verify</h3>
                  <p>These may describe genuine friction, but the evidence does not establish confirmed product defects.</p>
                  {observations.length
                    ? <ul className="ledger-findings">{observations.map((f) => <ReportFinding key={f.id} finding={f} runId={run.id}/>)}</ul>
                    : <p>No unverified observations were recorded.</p>}
                </section>
                <section id="report-reliability" className="ledger-section">
                  <span className="ledger-kicker">03 / Test quality</span>
                  <h3>Execution reliability</h3>
                  <p>Technical failures and access restrictions are not defects of the product under test. Similar symptoms are grouped; every original record remains accessible.</p>
                  {groups.size ? [...groups].map(([name, items]) => <details className="ledger-cluster" key={name}>
                    <summary><span>{name}</span><small>{items.length} {items.length === 1 ? "journey" : "journeys"}</small></summary>
                    <ul>{items.map((f) => <li key={f.id}>
                      <Link to={"/runs/" + run.id + "/findings/" + f.id}>{f.title}</Link>
                      <p>{f.summary}</p>
                    </li>)}</ul>
                  </details>) : <p>No test execution diagnostics were recorded.</p>}
                </section>
              </div>
              <aside className="ledger-aside" aria-label="Coverage and next action">
                <span className="ledger-kicker">Run coverage</span>
                <h3>What completed</h3>
                <p>{journeyTotal === null ? "Completion data unavailable." :
                  String(completed) + " of " + String(journeyTotal) + " journeys reached normal completion."}</p>
                {journeyTotal !== null && journeyTotal > 0 ? <>
                  <strong className="ledger-rate">{Math.round(100 * completed / journeyTotal)}%</strong>
                  <div className="ledger-progress" role="img" aria-label={String(completed) + " of " + String(journeyTotal) + " journeys completed execution"}>
                    <span style={{ width: String(100 * completed / journeyTotal) + "%" }}/>
                  </div>
                  <p className="ledger-fineprint">This is execution completion, not a product pass rate.</p>
                </> : null}
                <h4>What to do next</h4>
                {reliability.length ? <p>Inspect recorded steps and resolve test execution limitations before rerunning affected workflows.</p> : null}
                {observations.length ? <p>Compare the observations with their criteria and evidence.</p> : null}
                {!reliability.length && !observations.length ? <p>Review verified findings and the documented test scope.</p> : null}
                <Link to={"/runs/" + run.id + "/journeys"}>Inspect journeys <ArrowUpRight size={14} aria-hidden="true"/></Link>
              </aside>
            </div>
            {featureRun ? <section className="ledger-lower"><FeatureCases id="report-feature-cases" runId={run.id} userId={user.id}/></section> : null}
            <section id="report-outcomes" className="ledger-lower">
              <span className="ledger-kicker">04 / Recorded coverage</span><h3>Journey outcomes</h3>
              <p>Execution completion and product outcomes are separate measures. An unfinished journey is not a pass or a verified product failure.</p>
              {metrics.outcomes.length ? <dl className="ledger-outcomes">{metrics.outcomes.map(([outcome, count]) =>
                <div key={outcome}><dt>{outcome === "none" ? "Not reported" : outcome.replaceAll("_", " ")}</dt><dd>{count}</dd></div>)}</dl>
                : <p>Outcome counts are not available.</p>}
            </section>
            <section className="ledger-lower ledger-assessment">
              <span className="ledger-kicker">05 / Interpretation</span>
              <RunAssessmentView assessment={data.report.payload.assessment} runId={run.id}/>
            </section>
            {data.report.executive_summary ? <details className="ledger-original">
              <summary>Read the original generated executive summary</summary>
              <p>{data.report.executive_summary}</p>
            </details> : null}
            <section id="report-scope" className="ledger-lower">
              <span className="ledger-kicker">06 / Method and provenance</span>
              <h3>What this report does—and doesn't—prove</h3>
              <p>{metrics.deterministic
                ? "This report was generated from deterministic evaluation checks. "
                : "This report contains the evaluation recorded for this test. "}
                Simulated testers are not real customers. Unverified outcomes cannot establish that a feature worked or failed.
                Evidence links and documented scope determine what can be concluded.</p>
              <dl className="ledger-identifiers">
                <div><dt>Report ID</dt><dd>{data.report.id}</dd></div>
                <div><dt>Test ID</dt><dd>{run.id}</dd></div>
              </dl>
            </section>
          </article>
        </div>
      ) : null}
    </ResultsBoundary>
  );
}

import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import {
  FileText,
  ArrowUpRight,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  ChevronRight,
} from "lucide-react";
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
  reportVerdict,
  sortFindings,
} from "../../lib/results";
import type { Finding } from "../../lib/api";

function ReportFindingCard({ finding, runId }: { finding: Finding; runId: string }) {
  const classification = findingClassification(finding);
  const isConfirmed = isConfirmedFinding(finding);
  return (
    <li className="ledger-finding-card">
      <div className="ledger-finding-meta">
        <StatusBadge status={finding.severity} />
        <span>{classification} · {finding.category.replaceAll("_", " ")}</span>
      </div>
      <h4>
        <Link to={`/runs/${runId}/findings/${finding.id}`}>
          {finding.title}
          <ArrowUpRight size={15} aria-hidden="true" />
        </Link>
      </h4>
      <p>{finding.summary}</p>
      {finding.recommendation ? (
        <p><strong>Recommendation: </strong>{finding.recommendation}</p>
      ) : null}
      <div className="ledger-finding-actions">
        {finding.evidence.step_ids.length > 0 && finding.journey_ids[0] ? (
          <Link
            to={`/runs/${runId}/journeys/${finding.journey_ids[0]}?step=${finding.evidence.step_ids[0]}`}
            className="ledger-evidence-link"
          >
            Inspect step {finding.evidence.step_ids[0]} evidence →
          </Link>
        ) : (
          <span className="ledger-fineprint">
            {isConfirmed ? classification : "Unverified observation"}
          </span>
        )}
        <span className="ledger-fineprint">
          {finding.journey_ids.length} {finding.journey_ids.length === 1 ? "journey" : "journeys"} affected
        </span>
      </div>
    </li>
  );
}

export function RunReportPage() {
  const { run, results, user } = useOutletContext<RunContext>();
  const data = results.status === "ready" ? results.data : null;
  const metrics = data ? reportMetrics(data) : null;
  const featureRun =
    data?.report.payload.mode === "deep_feature_v1" ||
    run.configuration_snapshot.execution_mode === "deep_feature_v1";

  if (!data || !metrics) {
    return <ResultsBoundary>{null}</ResultsBoundary>;
  }

  // Findings Partitioning
  const verifiedFindings = sortFindings(data.findings.filter(isConfirmedFinding));
  const diagnostics = data.findings.filter(
    (f) =>
      findingClassification(f) === "Test execution issue" ||
      ["policy", "execution_reliability"].includes(f.category)
  );
  const observations = sortFindings(
    data.findings.filter((f) => !isConfirmedFinding(f) && !diagnostics.includes(f))
  );

  // Grouped Diagnostics (cluster similar timeouts/errors)
  const diagnosticClusters = new Map<string, Finding[]>();
  for (const item of diagnostics) {
    const key = item.title || item.category || "Execution Diagnostic";
    const existing = diagnosticClusters.get(key) ?? [];
    existing.push(item);
    diagnosticClusters.set(key, existing);
  }

  const verdict = reportVerdict(data);
  const { completed, total: journeyTotal, completionRate } = verdict;

  return (
    <ResultsBoundary>
      <div className="evidence-ledger">
        <article className="ledger-paper">
          {/* Evidence-based result */}
          <div
            id="report-verdict"
            className={`ledger-verdict-banner verdict-${verdict.tone}`}
            role="region"
            aria-label="Test result"
          >
            <div className="verdict-header-row">
              <span className="verdict-status-pill">
                {verdict.tone === "failed" ? (
                  <ShieldAlert size={16} aria-hidden="true" />
                ) : verdict.tone === "caution" ? (
                  <AlertTriangle size={16} aria-hidden="true" />
                ) : (
                  <CheckCircle2 size={16} aria-hidden="true" />
                )}
                {verdict.label}
              </span>
              {data.report.executive_summary ? (
                <CopyButton
                  text={data.report.executive_summary}
                  label="Copy generated summary"
                />
              ) : null}
            </div>
            <h2 className="verdict-title">{verdict.title}</h2>
            <p className="verdict-subtitle">{verdict.description}</p>
            <p className="ledger-fineprint">
              Version {data.report.version} ·{" "}
              <time dateTime={data.report.generated_at ?? undefined}>
                Generated {formatDate(data.report.generated_at)}
              </time>
            </p>
            <nav className="inline-actions" aria-label="Report findings">
              <a className="secondary-button compact" href="#report-verified">
                {verifiedFindings.length} verified {verifiedFindings.length === 1 ? "issue" : "issues"}
              </a>
              <a className="secondary-button compact" href="#report-observations">
                {observations.length} to review
              </a>
              <a className="secondary-button compact" href="#report-reliability">
                {diagnostics.length} execution {diagnostics.length === 1 ? "issue" : "issues"}
              </a>
            </nav>
          </div>

          {/* Two-Column Body */}
          <div className="ledger-columns">
            <div className="ledger-main">
              {/* Section 01: Verified Defect Findings */}
              <section id="report-verified" className="ledger-section">
                <h3>Verified product issues</h3>
                {verifiedFindings.length > 0 ? (
                  <ul className="ledger-findings">
                    {verifiedFindings.map((f) => (
                      <ReportFindingCard key={f.id} finding={f} runId={run.id} />
                    ))}
                  </ul>
                ) : (
                  <div className="ledger-finding-card">
                    <p>
                      No verified product issues recorded. Review the coverage and any
                      unverified observations before drawing conclusions.
                    </p>
                  </div>
                )}
              </section>

              {/* Section 02: Observations to Verify */}
              <section id="report-observations" className="ledger-section">
                <span className="ledger-kicker">02 / Further Investigation</span>
                <h3>Observations to Verify</h3>
                <p>
                  These items have not met this report's evidence requirements for a
                  verified product issue. Inspect their evidence before drawing conclusions.
                </p>
                {observations.length > 0 ? (
                  <ul className="ledger-findings">
                    {observations.map((f) => (
                      <ReportFindingCard key={f.id} finding={f} runId={run.id} />
                    ))}
                  </ul>
                ) : (
                  <p className="ledger-fineprint">No unverified observations were recorded.</p>
                )}
              </section>

              {/* Section 03: Execution Reliability */}
              <section id="report-reliability" className="ledger-section">
                <span className="ledger-kicker">03 / Test Quality</span>
                <h3>Execution Reliability</h3>
                <p>
                  Technical interruptions (timeouts, origin policy denials, tool errors)
                  are limitations of the test run, <strong>not defects of the product</strong>.
                  Similar issues are grouped below:
                </p>
                {diagnosticClusters.size > 0 ? (
                  [...diagnosticClusters.entries()].map(([title, items]) => (
                    <details className="ledger-cluster" key={title}>
                      <summary>
                        <span>{title}</span>
                        <small>
                          {items.length} {items.length === 1 ? "journey" : "journeys"}
                        </small>
                      </summary>
                      <ul>
                        {items.map((item) => (
                          <li key={item.id}>
                            <Link to={`/runs/${run.id}/findings/${item.id}`}>
                              {item.title}
                            </Link>
                            <p>{item.summary}</p>
                          </li>
                        ))}
                      </ul>
                    </details>
                  ))
                ) : (
                  <p className="ledger-fineprint">
                    No test execution diagnostics or timeouts were recorded.
                  </p>
                )}
              </section>
            </div>

            {/* Sticky Aside Rail */}
            <aside className="ledger-aside" aria-label="Coverage and next action">
              <span className="ledger-kicker">Execution Coverage</span>
              <h3>Completion Rate</h3>
              <p>
                {journeyTotal === 0
                  ? "No journeys recorded."
                  : completionRate === null
                  ? "Completion data unavailable."
                  : `${completed} of ${journeyTotal} journeys completed normally.`}
              </p>
              {completionRate !== null ? (
                <>
                  <div className="ledger-rate-display">
                    <strong className="ledger-rate">{completionRate}%</strong>
                    <span className="ledger-fineprint">finished</span>
                  </div>
                  <div
                    className="ledger-progress"
                    role="progressbar"
                    aria-valuenow={completionRate}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`${completed} of ${journeyTotal} journeys finished`}
                  >
                    <span style={{ width: `${completionRate}%` }} />
                  </div>
                  <p className="ledger-fineprint">
                    Execution completion is an operational measure, not a product pass rate.
                  </p>
                </>
              ) : null}

              <h4>Recommended Next Action</h4>
              {diagnostics.length > 0 ? (
                <p>
                  Review execution logs or target origin authorization to eliminate timeouts
                  before rerunning affected journeys.
                </p>
              ) : verifiedFindings.length > 0 ? (
                <p>
                  Inspect the cited steps and screenshots for verified defects, then triage
                  remediations with engineering.
                </p>
              ) : (
                <p>
                  Review the documented scope and criteria coverage to expand test depth.
                </p>
              )}
              <Link to={`/runs/${run.id}/journeys`} className="ledger-aside-cta">
                Inspect Journeys <ArrowUpRight size={14} aria-hidden="true" />
              </Link>
            </aside>
          </div>

          {/* Feature Cases (if deep_feature_v1) */}
          {featureRun ? (
            <section id="report-feature-cases" className="ledger-lower">
              <span className="ledger-kicker">Feature Verification</span>
              <FeatureCases id="report-feature-cases-table" runId={run.id} userId={user.id} />
            </section>
          ) : (
            <section id="report-outcomes" className="ledger-lower">
              <span className="ledger-kicker">04 / Recorded Coverage</span>
              <h3>Journey Outcomes</h3>
              <p>
                Execution status and evaluated product outcomes are separate measures.
                An unfinished journey is neither a pass nor a confirmed product bug.
              </p>
              {metrics.outcomes.length > 0 ? (
                <dl className="ledger-outcomes">
                  {metrics.outcomes.map(([outcome, count]) => (
                    <div key={outcome} className="ledger-outcome-card">
                      <dt>{outcome === "none" ? "Not reported" : outcome.replaceAll("_", " ")}</dt>
                      <dd>{count}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="ledger-fineprint">Outcome counts are not available.</p>
              )}
            </section>
          )}

          {/* Assessment Section */}
          <section id="report-assessment" className="ledger-lower">
            <span className="ledger-kicker">05 / Synthesis</span>
            <h3>Evaluator Assessment</h3>
            <RunAssessmentView assessment={data.report.payload.assessment} runId={run.id} />
          </section>

          {/* Original Executive Summary Disclosure */}
          {data.report.executive_summary ? (
            <details className="ledger-original">
              <summary>Read full generated narrative summary</summary>
              <p>{data.report.executive_summary}</p>
            </details>
          ) : null}

          {/* Scope & Provenance */}
          <details id="report-scope" className="ledger-original">
            <summary>Scope, method and report identifiers</summary>
            <p>
              {metrics.deterministic
                ? "This report was generated from deterministic evaluation checks. "
                : "This report contains the evaluation recorded for this test. "}
              Simulated testers are hypothesis-driven testing agents, not real customers.
              Unverified outcomes cannot establish that a flow works or fails in production.
              Verified assertions and exact cited evidence determine what can be concluded.
            </p>
            <dl className="ledger-identifiers">
              <div>
                <dt>Report ID</dt>
                <dd className="monospace">{data.report.id}</dd>
              </div>
              <div>
                <dt>Test ID</dt>
                <dd className="monospace">{run.id}</dd>
              </div>
              <div>
                <dt>Mode</dt>
                <dd className="monospace">
                  {typeof data.report.payload.mode === "string"
                    ? data.report.payload.mode
                    : typeof run.configuration_snapshot.execution_mode === "string"
                    ? run.configuration_snapshot.execution_mode
                    : "standard"}
                </dd>
              </div>
            </dl>
          </details>
        </article>
      </div>
    </ResultsBoundary>
  );
}

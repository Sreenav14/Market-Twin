import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useOutletContext } from "react-router-dom";
import { FeatureCases } from "../../components/markettwin/FeatureCases";
import { StackedBar, type BarSegment } from "../../components/markettwin/ResultFigures";
import { ResultsBoundary } from "../../components/markettwin/ResultsBoundary";
import { SlopEntryAssessment } from "../../components/markettwin/SlopEntryAssessment";
import type { RunContext } from "../../layouts/RunLayout";
import { api, type RunResults, type TestRun } from "../../lib/api";
import { statusEntry } from "../../lib/status";
import { ContractReport } from "./ContractReport";
import { HarnessReport } from "./HarnessReport";
import { PersonaImpressions, PersonaTakeaway, PersonaTasks } from "./PersonaImpressions";
import {
  Disclosure, FirstFindings, ReportActivity, ReportDiff, ReportEyebrow, ReportFacts,
  ReportFindings, ReportFrame, count, record, records, reportKind, reportScopePartial, useReportFlow, useReportHandoffs,
} from "./ReportFrame";
import { SlopReport, lookDiffItems, type SlopReportPayload } from "./SlopReport";

function findingDiffItems(results: RunResults) {
  return results.findings.map(item => ({
    key: JSON.stringify([item.finding_kind, item.category, item.title]),
    label: item.title, severity: item.severity, href: `/runs/${results.test_run_id}/findings/${item.id}`,
  }));
}

function SavedReport({ run, data, userId }: { run: TestRun; data: RunResults; userId: string }) {
  const { hash } = useLocation();
  const { report, findings } = data;
  const { payload } = report;
  const kind = reportKind(payload, run);
  const coverage = record(payload.coverage);
  const boardCoverage = record(record(payload.board).coverage);
  const budgets = record(payload.budget_counters);
  const totals = record(payload.findings);
  const flow = useReportFlow(run, userId);
  const handoffs = useReportHandoffs(run.id, userId);
  const journeys = useQuery({
    queryKey: ["journeys", userId, run.id],
    queryFn: ({ signal }) => api.getRunJourneys(run.id, signal),
    enabled: kind === "explore_test",
    retry: false,
  });
  const eyebrow = <ReportEyebrow run={run} kind={kind} />;
  const getItems = kind === "slop"
    ? (result: RunResults) => lookDiffItems(result.report.payload as SlopReportPayload, result.test_run_id)
    : findingDiffItems;
  const rerunDiff = <ReportDiff run={run} userId={userId} kind={kind} items={getItems(data)} getItems={getItems}
    partial={reportScopePartial(payload)} desktopOnly={kind === "slop" && coverage.desktop_scan === true} />;
  const activity = <ReportActivity flow={flow.data} coverage={coverage} slop={kind === "slop"} handoffs={handoffs.data}
    checkpoints={payload.activity_checkpoints} />;
  const facts = <ReportFacts run={run} report={report}>
    {kind === "contract" && payload.contract_version != null && typeof payload.contract_hash === "string" ?
      <p>contract v{count(payload.contract_version) ?? String(payload.contract_version)} · {payload.contract_hash}</p> : null}
    {kind === "persona" && count(record(payload.collection).model_calls) !== undefined ?
      <p>{count(record(payload.collection).model_calls)} model calls</p> : null}
    {kind === "explore_test" && typeof budgets.items_started === "number" && typeof budgets.item_budget === "number" ?
      <p>Item budget · {count(budgets.items_started)} used · {count(Math.max(0, budgets.item_budget - budgets.items_started))} remaining</p> : null}
  </ReportFacts>;
  const technical = <>
    {kind !== "slop" ? <p className="button-row">
      <Link to="?view=evaluation">Evaluation records</Link>
      <Link to="?view=perspectives">Tester perspectives</Link>
      <Link to="?view=findings">Findings list</Link>
    </p> : null}
    {flow.data ? <pre>{JSON.stringify({ edges: flow.data.edges, execution_policy: flow.data.execution_policy, revision: flow.data.revision }, null, 2)}</pre> : null}
    {totals.severity_counts ? <pre>{JSON.stringify(totals.severity_counts, null, 2)}</pre> : null}
    {(kind === "legacy" || kind === "deep_feature_v1") && payload.assessment ? <>
      <h3>Model assessment</h3><pre>{JSON.stringify(payload.assessment, null, 2)}</pre>
    </> : null}
    {kind === "persona" ? records(payload.personas).flatMap(persona => records(persona.tasks).flatMap((task, index) => task.action_trace
      ? [<Disclosure key={`${persona.persona_id}-${index}`} label={`Action trace · ${persona.persona_name ?? "Persona"}`}>
        <pre>{JSON.stringify(task.action_trace, null, 2)}</pre>
      </Disclosure>] : [])) : null}
  </>;
  const frame = { rerunDiff, activity, facts, technical };
  const findingSections = {
    first: <FirstFindings runId={run.id} findings={findings} checked={kind === "explore_test" && boardCoverage.checked === boardCoverage.denominator &&
      record(boardCoverage.counts).broken === 0 ? count(boardCoverage.checked) : undefined} unit="checks" />,
    observations: <ReportFindings runId={run.id} findings={findings} totals={totals} evaluation={payload.evaluation_records} />,
  };
  if (kind === "slop") return <SlopReport {...frame} runId={run.id} hash={hash} eyebrow={eyebrow} payload={payload as SlopReportPayload} />;
  if (kind === "explore_test") return <HarnessReport {...frame} {...findingSections} eyebrow={eyebrow}
    runId={run.id} payload={payload} summary={report.executive_summary} journeys={journeys.data ?? []} handoffs={handoffs.data} />;
  if (kind === "contract") return <ContractReport {...frame} {...findingSections} eyebrow={eyebrow} runId={run.id} payload={payload} />;
  if (kind === "persona") return <ReportFrame {...frame}
    takeaway={<>{eyebrow}<PersonaTakeaway payload={payload} /></>}
    middle={<PersonaImpressions payload={payload} />}
    inventory={<PersonaTasks payload={payload} />} />;

  const journeyStats = record(payload.journeys);
  const feature = kind === "deep_feature_v1";
  const composition = feature ? coverage : record(journeyStats.outcome_counts);
  const keys = feature ? ["passed", "failed_cases", "blocked", "inconclusive", "not_run"] : ["passed", "failed", "partial", "inconclusive", "none"];
  const total = feature ? coverage.planned : journeyStats.total;
  const segments = keys.flatMap((key): BarSegment[] => {
    const value = composition[key];
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return [];
    const status = key === "failed_cases" ? { word: "Failed", tone: "broken" } as const
      : key === "not_run" ? { word: "Not checked", tone: "notchecked" } as const
      : key === "blocked" ? { word: "Blocked", tone: "notchecked" } as const
      : key === "none" ? { word: "Not recorded", tone: "notchecked" } as const
      : statusEntry("journeyOutcome", key);
    return [{ key, count: value, ...status }];
  });
  const totalAccountsForOutcomes = typeof total === "number" && total > 0 && segments.reduce((sum, item) => sum + item.count, 0) === total;
  const assertionsFailed = count(coverage.failed_assertions);
  const middle = totalAccountsForOutcomes || (feature && (count(total) !== undefined || assertionsFailed !== undefined)) ?
    <section className="report-section"><h2>{feature ? "Case outcomes" : "Journey outcomes"}</h2>
      {totalAccountsForOutcomes ? <StackedBar segments={segments} total={total} unit={feature ? "cases" : "journeys"} /> : <>
        {count(total) !== undefined ? <p>{count(total)} cases planned</p> : null}
        {segments.length ? <dl>{segments.map(outcome => <div key={outcome.key}><dt>{outcome.word}</dt><dd>{count(outcome.count)} cases</dd></div>)}</dl> : null}
      </>}
      {feature && assertionsFailed !== undefined ? <dl><div><dt>Failed assertions</dt><dd>{assertionsFailed}</dd></div></dl> : null}
    </section> : null;
  return <ReportFrame {...frame} {...findingSections} middle={middle}
    takeaway={<>{eyebrow}{report.executive_summary ? <h2 className="report-verdict">{report.executive_summary}</h2> : null}
      {!feature ? <p role="note">This report was produced by the older exploratory mode. Its findings are unverified observations.</p> : null}</>}
    inventory={feature ? <Disclosure id="report-feature-cases" label="Feature cases" initiallyOpen={hash === "#report-feature-cases"}>
      <FeatureCases runId={run.id} userId={userId} showCoverage={!middle} />
    </Disclosure> : null} />;
}

export function RunReportPage() {
  const { run, results, user } = useOutletContext<RunContext>();
  if (results.status === "loading") return <article className="report-frame" role="status" aria-label="Loading results">
    <div className="report-takeaway report-skeleton" aria-hidden="true"><span /><span /><span /></div>
  </article>;
  return <>
    {results.status === "waiting" ? <SlopEntryAssessment runId={run.id} snapshot={run.configuration_snapshot} /> : null}
    <ResultsBoundary>{results.status === "ready" ? <SavedReport run={run} data={results.data} userId={user.id} /> : null}</ResultsBoundary>
  </>;
}

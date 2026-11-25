import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { StatusBadge, SeverityBadge } from "../../components/ui/StatusBadge";
import type { RunFlow } from "../../components/markettwin/RunFlowPanel";
import { api, request, type Finding, type TestRun } from "../../lib/api";
import { formatDate, severityRank, sortFindings, terminalTestStatuses } from "../../lib/results";
import { testReference } from "../../lib/format";
import { FINDING_STATUS, statusEntry, type StatusTone } from "../../lib/status";
import "../../styles/results-frame.css";

export const number = (value: number) => value.toLocaleString("en-US");
export function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
export function records(value: unknown) {
  return Array.isArray(value) ? value.map(record) : [];
}
export function text(value: unknown) {
  return typeof value === "string" ? value : undefined;
}
export function count(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? number(value) : undefined;
}

type Kind = "slop" | "explore_test" | "contract" | "persona" | "legacy" | "deep_feature_v1";
type VerdictKind = "harness" | "shipping" | "contract" | "slop";
const verdictWords: Record<string, [string, StatusTone]> = {
  ready: ["Ready", "works"],
  not_ready: ["Not ready yet", "broken"],
  insufficient_evidence: ["Can't tell yet", "notchecked"],
};
const harnessWords: typeof verdictWords = {
  ...verdictWords,
  Ready: verdictWords.ready,
  "Not ready yet": verdictWords.not_ready,
  "Can't tell yet": verdictWords.insufficient_evidence,
};
export const VERDICT_WORDS = {
  harness: harnessWords,
  shipping: verdictWords,
  contract: { ...verdictWords, ready_with_issues: ["Ready, with issues", "couldnot"] as [string, StatusTone] },
  slop: {
    scored: ["Measured", "works"],
    coverage_incomplete: ["Coverage incomplete — no percentage yet", "notchecked"],
    no_judged_elements: ["No elements judged", "notchecked"],
  },
} satisfies Record<VerdictKind, typeof verdictWords>;

export function ReportStatus({ word, tone }: { word: string; tone: StatusTone }) {
  const glyph = { works: "✓", broken: "×", couldnot: "!", notchecked: "–", info: "·" }[tone];
  return <span className={`report-status report-status-${tone}`}><span aria-hidden="true">{glyph}</span> {word}</span>;
}

export function Verdict({ value, kind, prefix, inline, id, className }: {
  value: unknown; kind: VerdictKind; prefix?: string; inline?: boolean; id?: string; className?: string;
}) {
  const map: typeof verdictWords = VERDICT_WORDS[kind];
  const key = text(value) ?? "";
  const entry = Object.hasOwn(map, key) ? map[key] : undefined;
  if (prefix && !entry) return null;
  const [word, tone] = entry ?? ["No verdict recorded in this report", "notchecked"];
  if (inline) return <ReportStatus word={word} tone={tone} />;
  if (prefix) return <p className="report-gate">{prefix} <ReportStatus word={word} tone={tone} /></p>;
  return <h2 id={id} className={className ?? "report-verdict"}><ReportStatus word={word} tone={tone} /></h2>;
}

export function KeyFigures({ figures }: { figures: { label: string; value: ReactNode }[] }) {
  return <dl className="report-key-figures">
    {figures.slice(0, 3).map(({ label, value }) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
  </dl>;
}

export function Disclosure({ label, children, id, initiallyOpen = false }: {
  label: ReactNode; children: ReactNode; id?: string; initiallyOpen?: boolean;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  return <details id={id} open={open} onToggle={(event) => setOpen(event.currentTarget.open)}><summary>{label}</summary>{open ? children : null}</details>;
}

interface FrameProps {
  takeaway: ReactNode;
  rerunDiff?: ReactNode;
  activity?: ReactNode;
  first?: ReactNode;
  middle?: ReactNode;
  coverage?: ReactNode;
  observations?: ReactNode;
  inventory?: ReactNode;
  facts?: ReactNode;
  technical?: ReactNode;
}

export function ReportFrame({ takeaway, rerunDiff, activity, first, middle, coverage, observations, inventory, facts, technical }: FrameProps) {
  return <article className="report-frame result-paper">
    <section className="report-takeaway" aria-label="Takeaway">{takeaway}</section>
    {rerunDiff}{activity}{first}{middle}{coverage}{observations}{inventory}{facts}
    <Disclosure label="Technical details">{technical}</Disclosure>
  </article>;
}

const kindWords: Record<Kind, string> = {
  slop: "Check the look",
  explore_test: "Explore & Test",
  contract: "Contract test",
  persona: "Persona test",
  legacy: "Test results",
  deep_feature_v1: "Feature test",
};

export function reportKind(payload: Record<string, unknown>, run: TestRun): Kind {
  const mode = payload.mode ?? run.configuration_snapshot?.execution_mode;
  const kind = payload.run_kind ?? run.run_kind;
  if (mode === "discovery_contract_v1" || kind === "contract") return "contract";
  if (mode === "harness_v1" || kind === "explore_test") return "explore_test";
  if (kind === "slop" || kind === "persona") return kind;
  if (mode === "slop" || mode === "persona") return mode;
  return mode === "deep_feature_v1" ? mode : "legacy";
}

export function ReportEyebrow({ run, kind }: { run: TestRun; kind: Kind }) {
  let host: string | undefined;
  const url = text(run.target_snapshot?.base_url);
  if (url) {
    try { host = new URL(url).host; } catch { host = undefined; }
  }
  return <p className="report-eyebrow">{[kindWords[kind], host].filter(Boolean).join(" · ")} · <ReportStatus {...statusEntry("run", run.status)} /></p>;
}

export function useReportFlow(run: TestRun, userId: string, ready = true) {
  return useQuery({
    queryKey: ["run-flow", userId, run.id, run.status, ready],
    queryFn: ({ signal }) => request<RunFlow>(`/api/v1/test-runs/${run.id}/flow`, { signal }),
    refetchInterval: !ready && run.status !== "draft" && !terminalTestStatuses.has(run.status) ? 5000 : false,
    retry: false,
  });
}

export interface ReportHandoffs {
  human_requests?: Record<string, number>;
  action_approvals?: Record<string, number>;
  role_coverage?: { role: string; planned: number; authenticated: number; executed: number; passed: number; blocked: number; inconclusive: number; not_run: number }[];
  inventory?: { feature_key: string; asserted_cases: number; not_explored: number }[];
  truncated?: boolean;
  executor_mode?: string;
  reused_auth_cases?: number;
}

export function useReportHandoffs(runId: string, userId: string) {
  return useQuery({
    queryKey: ["hitl-summary", userId, runId],
    queryFn: ({ signal }) => request<ReportHandoffs>(`/api/v1/test-runs/${runId}/hitl-summary`, { signal }),
    retry: false,
  });
}

const stopWords: Record<string, string> = {
  frontier_exhausted: "All discovered pages were checked",
  budget_exhausted: "Stopped — the run's budget ran out",
  owner_stopped: "Stopped by you",
  all_lanes_retired: "All scan lanes finished or retired",
  time_budget: "Stopped — the run's budget ran out",
};

export function ReportActivity({ flow, coverage, slop, handoffs, checkpoints }: {
  flow: RunFlow | undefined; coverage: Record<string, unknown>; slop?: boolean; handoffs?: ReportHandoffs; checkpoints?: unknown;
}) {
  const [selected, setSelected] = useState<string>();
  const nodes = flow?.nodes ?? [];
  const stages = slop ? [
    { id: "discover", label: "Discover", status: (nodes.find(node => node.kind === "discovery") ?? nodes.find(node => node.kind === "meta"))?.status },
    { id: "inspect", label: "Inspect", status: nodes.find(node => node.kind === "journey")?.status },
    { id: "verify", label: "Verify", status: nodes.find(node => node.id === "evaluation")?.status },
    { id: "report", label: "Report", status: nodes.find(node => node.id === "report")?.status },
  ] : nodes;
  const active = stages.some(stage => stage.id === selected) ? selected : stages.at(-1)?.id;
  const terminal = active === stages.at(-1)?.id;
  const humanWait = record(coverage.desktop_budget).human_wait_seconds;
  const captions = [...new Set([
    Object.hasOwn(stopWords, text(coverage.stop_reason) ?? "") ? stopWords[text(coverage.stop_reason)!] : undefined,
    coverage.owner_stopped && "Stopped by you",
    coverage.budget_exhausted && "Stopped — the run's budget ran out",
    typeof humanWait === "number" && humanWait > 0 && `Waited ${number(Math.round(humanWait))} seconds for a person to act`,
    coverage.all_lanes_retired && "All scan lanes finished or retired",
  ].filter((caption): caption is string => typeof caption === "string"))];
  return <section className="report-section" aria-label="Agent activity">
    <h2>Agent activity</h2>
    {nodes.length ? <ol className="report-steps">{stages.map(node => <li key={node.id}>
      <button type="button" aria-pressed={active === node.id} onClick={() => setSelected(node.id)}>
        <strong>{node.label}</strong><StatusBadge source="flow" status={node.status ?? "not_recorded"} />
      </button>
    </li>)}</ol> : <p>No agent activity recorded.</p>}
    {[...Object.values(handoffs?.human_requests ?? {}), ...Object.values(handoffs?.action_approvals ?? {})].some(value => value > 0) ?
      <ReportStatus word="Human handoff" tone="info" /> : null}
    {terminal && captions.length ? <p aria-live="polite">{captions.join(" · ")}</p> : null}
    {terminal && records(checkpoints).length ? <Disclosure label="Review points">
      <ul>{records(checkpoints).map((point, i) => <li key={i}>{[point.decision === "continue" ? "Continue" : point.decision === "stop" ? "Stop" : undefined, text(point.reason)].filter(Boolean).join(" · ")}</li>)}</ul>
    </Disclosure> : null}
  </section>;
}

export function ReportFacts({ run, report, children }: {
  run: TestRun;
  report: { id: string; generated_at: string | null; payload: Record<string, unknown> };
  children?: ReactNode;
}) {
  const { payload } = report;
  const shape = [payload.schema_version, payload.mode, payload.generator].filter(item => typeof item === "string" || typeof item === "number");
  return <section className="report-facts" aria-label="Run facts">
    <h2>Run facts</h2>
    <p>{testReference(run)} · Report {report.id}{report.generated_at ? <> · report generated <time dateTime={report.generated_at}>{formatDate(report.generated_at)}</time></> : null}{shape.length ? <> · {shape.join(" · ")}</> : null}</p>
    {children}
  </section>;
}

const categories: Record<string, string> = {
  accessibility: "Accessibility", functional: "Functionality", functionality: "Functionality",
  policy: "Test policy", execution_reliability: "Execution reliability", usability: "Usability",
  performance: "Performance", visual: "Visual", visual_criterion: "Visual check", content: "Content", navigation: "Navigation",
  reliability: "Reliability", trust: "Trust", onboarding: "Onboarding", pricing: "Pricing",
};

export function findingPartition(finding: Finding) {
  if (finding.finding_kind === "test_execution_issue") return "diagnostics";
  if (finding.finding_kind === "observed_product_issue" && ["verified_deterministic", "verified_visual"].includes(finding.verification_status ?? "")) return "verified";
  return "observations";
}

function FindingEvidence({ runId, finding }: { runId: string; finding: Finding }) {
  const step = finding.evidence?.step_ids?.[0];
  const journey = finding.journey_ids?.length === 1 ? finding.journey_ids[0] : undefined;
  const artifact = finding.evidence?.artifact_ids?.[0];
  const to = typeof step === "number" && journey ? `/runs/${runId}/journeys/${journey}?step=${step}`
    : artifact && finding.journey_ids?.length <= 1 ? `/runs/${runId}/evidence/${artifact}` : `/runs/${runId}/findings/${finding.id}`;
  return <Link className="secondary-button compact" to={to}>View evidence</Link>;
}

export function FirstFindings({ runId, findings, checked, unit }: { runId: string; findings: Finding[]; checked?: string; unit?: string }) {
  const first = sortFindings(findings.filter(item => findingPartition(item) === "verified")).slice(0, 3);
  if (!first.length) return checked && checked !== "0" && unit && findings.length === 0
    ? <section className="report-section"><h2>What to check first</h2><p>Nothing needs fixing first — {checked} {unit} were inspected.</p></section>
    : null;
  return <section className="report-section"><h2>What to check first</h2>
    <p>Most severe findings first.</p>
    <ul className="report-rows">{first.map(item => <li key={item.id}>
      <strong>{item.title}</strong> <SeverityBadge severity={item.severity} />
      {item.recommendation ? <p>{item.recommendation}</p> : null}
      <FindingEvidence runId={runId} finding={item} />
    </li>)}</ul>
  </section>;
}

const groupLabels = {
  verified: ["Verified", "confirmed_issue_count"],
  observations: ["Observations", "unverified_observation_count"],
  diagnostics: ["Diagnostics", "execution_diagnostic_count"],
} as const;

export function ReportFindings({ runId, findings, totals, evaluation }: {
  runId: string; findings: Finding[]; totals: Record<string, unknown>; evaluation?: unknown;
}) {
  const [category, setCategory] = useState<string>();
  const checks = records(evaluation).filter(item => item.kind === "visual");
  if (!findings.length && !Object.keys(totals).length && !checks.length) return null;
  return <section className="report-section" id="report-findings"><h2>Observations and diagnostics</h2>
    <div className="report-controls">{Object.entries(record(totals.category_counts)).filter(([key]) => Object.hasOwn(categories, key)).map(([key, value]) =>
      <button key={key} type="button" aria-pressed={key === category} onClick={() => setCategory(key === category ? undefined : key)}>{categories[key]} · {count(value)}</button>
    )}</div>
    {(Object.keys(groupLabels) as Array<keyof typeof groupLabels>).map(group => {
      const [label, key] = groupLabels[group];
      const items = sortFindings(findings.filter(item => findingPartition(item) === group && (!category || item.category === category)));
      return <Disclosure key={group} label={count(totals[key]) === undefined ? label : `${label} · ${count(totals[key])}`}>
        <ul className="report-rows">{items.map(item => {
          const classification = group === "diagnostics" ? "Test execution issue" : group === "observations" ? "Needs Verification" : item.verification_status === "verified_visual" ? "Visually verified issue" : "Verified assertion issue";
          const status = item.verification_status ?? "";
          const trust = Object.hasOwn(FINDING_STATUS, status) ? FINDING_STATUS[status] : { word: "Not recorded", tone: "notchecked" as const };
          return <li key={item.id}><Disclosure label={<>{item.title} <SeverityBadge severity={item.severity} /> {Object.hasOwn(categories, item.category) ? categories[item.category] : null} · {classification} · <ReportStatus {...trust} /></>}>
            <p>{item.summary}</p>
            {item.recommendation ? <p>What to do: {item.recommendation}</p> : null}
            {item.journey_ids?.map((id, index) => <Link key={id} to={`/runs/${runId}/journeys/${id}`}>Journey {index + 1} </Link>)}
            <FindingEvidence runId={runId} finding={item} />
          </Disclosure></li>;
        })}</ul>
        {!items.length ? <p>No findings in this group.</p> : null}
      </Disclosure>;
    })}
    {checks.length ? <Disclosure label="Visual checks"><ul className="report-rows">{checks.map((item, index) => {
      const words = { satisfied: "Satisfied", unsatisfied: "Not satisfied", unverified: "Not verified" } as const;
      const state = text(item.status) ?? "";
      const evidence = record(item.evidence);
      const journey = text(item.journey_id);
      const step = Array.isArray(evidence.step_ids) ? evidence.step_ids[0] : undefined;
      return <li key={index}><strong>{text(item.criterion)}</strong> · <ReportStatus
        word={Object.hasOwn(words, state) ? words[state as keyof typeof words] : "Not recorded"}
        tone={state === "satisfied" ? "works" : state === "unsatisfied" ? "broken" : "notchecked"} />
        {text(item.rationale) ? <p>{text(item.rationale)}</p> : null}
        {Array.isArray(item.observed_details) ? item.observed_details.map((detail, i) => text(detail) ? <p key={i}>{text(detail)}</p> : null) : null}
        {journey && typeof step === "number" ? <Link to={`/runs/${runId}/journeys/${journey}?step=${step}`}>View supporting step </Link> : null}
        {Array.isArray(evidence.artifact_ids) ? evidence.artifact_ids.map(id => text(id) ?
          <Link key={id} to={`/runs/${runId}/evidence/${encodeURIComponent(id)}`}>View evidence </Link> : null) : null}
      </li>;
    })}</ul></Disclosure> : null}
  </section>;
}

export interface DiffItem {
  key: string;
  label: string;
  severity?: Finding["severity"];
  href?: string;
}
export function reportScopePartial(payload: Record<string, unknown>) {
  const coverage = record(payload.coverage);
  const board = record(record(payload.board).coverage);
  const collection = record(payload.collection);
  return coverage.partial === true || collection.partial === true
    || (typeof board.checked === "number" && typeof board.denominator === "number" && board.checked < board.denominator)
    || (typeof coverage.tested_features === "number" && typeof coverage.discovered_features === "number" && coverage.tested_features < coverage.discovered_features);
}

export function ReportDiff({ run, userId, kind, items, getItems, partial, desktopOnly }: {
  run: TestRun; userId: string; kind: Kind; items: DiffItem[];
  getItems: (data: Awaited<ReturnType<typeof api.getRunResults>>) => DiffItem[];
  partial?: boolean;
  desktopOnly?: boolean;
}) {
  const history = useQuery({
    queryKey: ["report-history", userId, run.application_id],
    queryFn: () => api.listRuns(run.application_id),
    enabled: Boolean(run.application_id && run.target_id && (run.created_at || run.test_number)),
    retry: false,
  });
  const prior = history.data?.filter(candidate =>
    candidate.id !== run.id && candidate.target_id === run.target_id && candidate.status === "completed" &&
    reportKind({}, candidate) === kind &&
    (run.test_number && candidate.test_number
      ? candidate.test_number < run.test_number
      : Boolean(run.created_at && candidate.created_at && Date.parse(candidate.created_at) < Date.parse(run.created_at))),
  ).sort((a, b) => (b.test_number ?? 0) - (a.test_number ?? 0) || Date.parse(b.created_at ?? "") - Date.parse(a.created_at ?? ""))[0];
  const priorReport = useQuery({
    queryKey: ["results", userId, prior?.id],
    queryFn: ({ signal }) => api.getRunResults(prior!.id, signal),
    enabled: Boolean(prior),
    retry: false,
  });
  if (!prior || !priorReport.data) return null;
  const previous = new Map(getItems(priorReport.data).map(item => [item.key, item]));
  const current = new Map(items.map(item => [item.key, item]));
  const priorPartial = reportScopePartial(priorReport.data.report.payload);
  const groups = [
    { label: "New", rows: [...current.values()].filter(item => !previous.has(item.key)), uncertain: priorPartial },
    { label: "Still present", rows: [...current.values()].filter(item => previous.has(item.key)) },
    { label: "Resolved", rows: [...previous.values()].filter(item => !current.has(item.key)), uncertain: partial },
  ];
  return <section className="report-section">
    <h2>Since the previous run</h2>
    <p>Comparing <span className="monospace">{testReference(run)}</span> with <Link to={`/runs/${prior.id}`} className="monospace">{testReference(prior)}</Link>{prior.created_at ? <> · {formatDate(prior.created_at)}</> : null}</p>
    <div className="report-diff-groups">{groups.map(({ label, rows, uncertain }) => uncertain || rows.length === 0
      ? <p key={label}>{label} · {uncertain ? <ReportStatus word="Not verified" tone="notchecked" /> : "0"}</p>
      : <Disclosure key={label} label={`${label} · ${number(rows.length)}`}>
        <ul>{rows.sort((a, b) => severityRank(a.severity ?? "info") - severityRank(b.severity ?? "info")).map(item => <li key={item.key}>{item.severity ? <SeverityBadge severity={item.severity} /> : null} {item.href ? <Link to={item.href}>{item.label}</Link> : item.label}</li>)}</ul>
    </Disclosure>)}</div>
    <p className="muted">Same target{desktopOnly && record(record(priorReport.data.report.payload).coverage).desktop_scan === true
      ? " · Desktop only" : ""}.{priorPartial && partial
      ? " New and resolved findings could not be verified because both runs had partial coverage."
      : priorPartial ? " New findings could not be verified because the previous run had partial coverage."
        : partial ? " Resolved findings could not be verified because this run had partial coverage." : ""}</p>
  </section>;
}

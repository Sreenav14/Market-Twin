import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { StackedBar, type BarSegment } from "../../components/markettwin/ResultFigures";
import { ASSERTION_STATUS, HARNESS_ITEM_STATUS, statusEntry } from "../../lib/status";
import type { JourneyExecution } from "../../lib/api";
import { count, Disclosure, number, record, records, ReportFrame, ReportStatus, text, Verdict, type ReportHandoffs } from "./ReportFrame";

const outcomes = ["broken", "could_not_check", "not_checked", "blocked", "worked", "owner_disabled"] as const;
const chartOrder = ["worked", "broken", "could_not_check", "not_checked", "blocked"] as const;
export const assertionWords: Record<string, string> = {
  outcome: "Outcome", visible: "Visible", enabled: "Enabled", url: "Address", text: "Text",
};
const safetyClasses: Record<string, string> = {
  read: "Read only", reversible: "Reversible change", irreversible: "Irreversible change",
};
const pageSize = 20;

function outcomeFor(value: unknown) {
  const key = text(value);
  if (key && Object.hasOwn(HARNESS_ITEM_STATUS, key)) {
    if (key === "blocked" || key === "could_not_check") return { word: HARNESS_ITEM_STATUS[key].word, tone: "notchecked" as const };
    return statusEntry("harnessItem", key);
  }
  return { word: "Outcome unavailable", tone: "notchecked" as const };
}

function journeyOutcome(journey: JourneyExecution) {
  if (journey.execution_status === "skipped") return { word: "Skipped", tone: "notchecked" as const };
  if (journey.outcome === "partial") return { word: "Partly", tone: "couldnot" as const };
  if (journey.outcome === "inconclusive") return { word: "Could not check", tone: "notchecked" as const };
  return journey.outcome ? statusEntry("journeyOutcome", journey.outcome) : { word: "Outcome unavailable", tone: "notchecked" as const };
}

function AuthenticatedCoverage({ handoffs }: { handoffs?: ReportHandoffs }) {
  if (!handoffs) return null;
  const requests = handoffs.human_requests ?? {};
  const approvals = handoffs.action_approvals ?? {};
  const asked = Object.values(requests).reduce((sum, amount) => sum + amount, 0);
  const requested = Object.values(approvals).reduce((sum, amount) => sum + amount, 0);
  return <section aria-label="Authenticated coverage">
    <h3>Authenticated coverage</h3>
    <p>{number(asked)} handoffs asked · {number(requests.completed ?? 0)} answered · {number(requests.expired ?? 0)} expired</p>
    <p>{number(requested)} approvals requested · {number((approvals.approved ?? 0) + (approvals.consumed ?? 0))} granted · {number(approvals.rejected ?? 0)} refused</p>
    {handoffs.role_coverage?.map(row => <p key={row.role}>
      {row.role} · {number(row.planned)} planned · {number(row.authenticated)} authenticated · {number(row.executed)} executed · {number(row.passed)} passed · {number(row.blocked)} blocked · {number(row.inconclusive)} could not check · {number(row.not_run)} not checked
    </p>)}
    {handoffs.inventory?.filter(item => item.not_explored > 0).map(item => <p key={item.feature_key}>
      {item.feature_key.replaceAll("_", " ")} · {number(item.asserted_cases)} cases with recorded assertions · {number(item.not_explored)} not explored
    </p>)}
    {handoffs.truncated ? <p role="status">This summary is truncated.</p> : null}
  </section>;
}

type Filters = { outcome?: string; tester?: string; task?: string; search?: string };

export function HarnessReport({ runId, payload, summary, journeys, handoffs, eyebrow, ...frame }: {
  runId: string;
  payload: Record<string, unknown>;
  summary: string | null;
  journeys: JourneyExecution[];
  handoffs?: ReportHandoffs;
  eyebrow: ReactNode;
} & Pick<Parameters<typeof ReportFrame>[0], "rerunDiff" | "activity" | "first" | "observations" | "facts" | "technical">) {
  const board = record(payload.board);
  const coverage = record(board.coverage);
  const items = records(board.items);
  const counts = record(coverage.counts);
  const denominator = typeof coverage.denominator === "number" ? coverage.denominator : undefined;
  const rowCounts = new Map<unknown, number>();
  for (const item of items) rowCounts.set(item.effective_status, (rowCounts.get(item.effective_status) ?? 0) + 1);
  const eligibleRows = items.length - (rowCounts.get("owner_disabled") ?? 0);
  const checkedRows = (rowCounts.get("worked") ?? 0) + (rowCounts.get("broken") ?? 0);
  const countsMatch = !Array.isArray(board.items) || (
    (denominator === undefined || denominator === eligibleRows)
    && (coverage.checked === undefined || coverage.checked === checkedRows)
    && (!Object.keys(counts).length || [...new Set([...Object.keys(counts), ...rowCounts.keys()])].every(key =>
      typeof key === "string" && (counts[key] ?? 0) === (rowCounts.get(key) ?? 0)))
  );
  const testerNames = [...new Set(journeys.map(journey => journey.persona_name))];
  const tasks = [...new Set(journeys.map(journey => journey.mission_title))];
  const [params, setParams] = useSearchParams();
  const outcome = outcomes.find(value => value === params.get("outcome"));
  const [localFilters, setFilters] = useState<Omit<Filters, "outcome">>({});
  const filters = { ...localFilters, outcome };
  const [pagination, setPagination] = useState({ outcome, page: 0 });
  const page = pagination.outcome === outcome ? pagination.page : 0;
  const setPage = (page: number) => setPagination({ outcome, page });
  function apply({ outcome: nextOutcome, ...next }: Filters) {
    setFilters(next);
    setPage(0);
    if (nextOutcome === outcome) return;
    setParams(previous => {
      const search = new URLSearchParams(previous);
      if (nextOutcome) search.set("outcome", nextOutcome);
      else search.delete("outcome");
      return search;
    }, { replace: true, preventScrollReset: true });
  }
  const matchingJourneys = journeys.filter(journey => (!filters.tester || journey.persona_name === filters.tester) && (!filters.task || journey.mission_title === filters.task));
  const journeyIds = new Set(matchingJourneys.map(journey => journey.id));
  const journeyCases = new Map<string, string>();
  const ambiguousCases = new Set<string>();
  for (const journey of journeys) {
    const caseId = text(journey.result?.case_id);
    if (!caseId) continue;
    if (journeyCases.has(caseId)) ambiguousCases.add(caseId);
    journeyCases.set(caseId, journey.id);
  }
  const itemJourney = (item: Record<string, unknown>) => {
    const caseId = text(item.case_id);
    return text(item.journey_id) ?? (caseId && !ambiguousCases.has(caseId) ? journeyCases.get(caseId) : undefined);
  };
  const sorted = items.filter(item => {
    const search = filters.search?.trim().toLowerCase();
    return (!filters.outcome || item.effective_status === filters.outcome)
      && (!(filters.tester || filters.task) || journeyIds.has(itemJourney(item) ?? ""))
      && (!search || (text(item.name) ?? "Unnamed check").toLowerCase().includes(search));
  }).sort((a, b) => {
    const priority = (status: unknown) => {
      const index = outcomes.findIndex(outcome => outcome === status);
      return index < 0 ? 3 : index;
    };
    return priority(a.effective_status) - priority(b.effective_status);
  });
  const segments: BarSegment[] = chartOrder.map(key => ({
    key,
    ...outcomeFor(key),
    count: typeof counts[key] === "number" ? counts[key] : 0,
  }));
  const completeComposition = countsMatch && denominator !== undefined && Object.keys(counts).length > 0
    && segments.reduce((sum, segment) => sum + segment.count, 0) === denominator;
  const selection = [filters.tester, filters.task, filters.outcome ? outcomeFor(filters.outcome).word : undefined].filter(Boolean);
  const pages = Math.ceil(sorted.length / pageSize);
  return <ReportFrame {...frame}
    takeaway={<>
      {eyebrow}
      <Verdict value={payload.verdict} kind="harness" />
      <Verdict value={record(payload.market_verdict).verdict} kind="shipping" prefix="For shipping:" />
      {summary ? <p>{summary}</p> : null}
      {countsMatch && count(coverage.checked) !== undefined && denominator !== undefined
        ? <p>Checked {count(coverage.checked)} of {number(denominator)} eligible checks (owner exclusions removed)</p>
        : <p>{number(items.length)} checks were recorded. Coverage is not available.</p>}
      {countsMatch && typeof coverage.missing_result_events === "number" && coverage.missing_result_events > 0 ?
        <p role="note">{number(coverage.missing_result_events)} finished checks have no recorded result — counted as could not check</p> : null}
    </>}
    middle={<section className="report-section">
      <h2>Check outcomes</h2>
      {completeComposition ? <StackedBar total={denominator} unit="checks" segments={segments}
        selected={filters.outcome} onSelect={outcome => apply({ ...filters, outcome: outcome ?? undefined })} /> : null}
      {!completeComposition && items.length > 0 ? <div className="report-controls" aria-label="Filter checks by outcome">
        {outcomes.filter(key => rowCounts.has(key)).map(key => <button key={key} type="button" aria-pressed={filters.outcome === key}
          onClick={() => apply({ ...filters, outcome: filters.outcome === key ? undefined : key })}>
          <ReportStatus {...outcomeFor(key)} /> · {number(rowCounts.get(key) ?? 0)}
        </button>)}
      </div> : null}
      {completeComposition && typeof counts.owner_disabled === "number" ? <p>Turned off by you — {number(counts.owner_disabled)}</p> : null}
      {testerNames.length ? <>
        <h3>Testers</h3>
        <div className="report-cards">{testerNames.map(name => {
          const testerJourneys = journeys.filter(journey => journey.persona_name === name);
          return <button key={name} type="button" aria-pressed={filters.tester === name} onClick={() => apply({ ...filters, tester: filters.tester === name ? undefined : name, task: undefined })}>
            <strong>{name}</strong> · {testerJourneys[0]?.persona_perspective}
            {testerJourneys.length === 1 ? <> · <ReportStatus {...journeyOutcome(testerJourneys[0])} /></> : null}
          </button>;
        })}</div>
        <Verdict value={payload.verdict} kind="harness" prefix="Put together — Verdict ·" />
        <div className="report-matrix" tabIndex={0} aria-label="Tester by task">
          <table><caption>Tester by task</caption><thead><tr><th scope="col">Tester</th>{tasks.map(task => <th key={task} scope="col">{task}</th>)}</tr></thead>
            <tbody>{testerNames.map(name => <tr key={name}><th scope="row">{name}</th>{tasks.map(task => {
              const cell = journeys.filter(journey => journey.persona_name === name && journey.mission_title === task);
              return <td key={task}>{cell.length ? <button type="button" aria-pressed={filters.tester === name && filters.task === task}
                onClick={() => apply({ ...filters, tester: name, task })}>
                {cell.map(journey => <ReportStatus key={journey.id} {...journeyOutcome(journey)} />)}
              </button> : "—"}</td>;
            })}</tr>)}</tbody>
          </table>
        </div>
      </> : <p>No tester-by-task outcomes were recorded for this run.</p>}
    </section>}
    coverage={<section className="report-section"><h2>Coverage</h2>
      {countsMatch && denominator !== undefined && count(coverage.checked) !== undefined ? <p>{count(coverage.checked)} of {number(denominator)} eligible checks recorded a worked or broken outcome.</p>
        : <p>Coverage could not be verified from the recorded checks.</p>}
      <AuthenticatedCoverage handoffs={handoffs} />
    </section>}
    inventory={<section className="report-section">
      <h2>Checks</h2>
      <label>Search checks <input type="search" value={filters.search ?? ""} onChange={event => apply({ ...filters, search: event.currentTarget.value })} /></label>
      {selection.length > 0 ? <p role="status">Showing: {selection.join(" · ")}</p> : null}
      {!sorted.length ? <p>{items.length ? <>No checks match. <button type="button" onClick={() => apply({})}>Clear filters</button></>
        : "No checks were recorded for this run."}</p> : <>
        {Object.values(filters).some(Boolean) ? <button type="button" onClick={() => apply({})}>Clear filters</button> : null}
        <ul className="report-rows">{sorted.slice(page * pageSize, (page + 1) * pageSize).map((item, index) => <li key={text(item.board_item_id) ?? index}>
          <Disclosure label={<><strong>{text(item.name) ?? "Unnamed check"}</strong> {text(item.role)} · <ReportStatus {...outcomeFor(item.effective_status)} /></>}>
            {text(item.blocker) ? <p>{text(item.blocker)}</p> : null}
            {item.missing_result_event === true ? <p>No result was recorded — counted as could not check.</p> : null}
            {item.board_status && item.board_status !== item.effective_status ? <p>Recorded status <ReportStatus {...outcomeFor(item.board_status)} /></p> : null}
            {records(item.assertions).length ? <ul>{records(item.assertions).map((assertion, i) => {
              const kind = text(assertion.kind) ?? "";
              const status = text(assertion.status) ?? "";
              return <li key={i}>{Object.hasOwn(assertionWords, kind) ? assertionWords[kind] : "Check"} · <ReportStatus
                {...(Object.hasOwn(ASSERTION_STATUS, status) ? ASSERTION_STATUS[status] : ASSERTION_STATUS["not reported"])} /> {text(assertion.detail)}</li>;
            })}</ul> : <p>No assertions were recorded for this check</p>}
            {Array.isArray(item.evidence_refs) ? item.evidence_refs.map((ref, i) => {
              const artifact = text(record(ref).artifact_id) ?? text(ref);
              return artifact ? <p key={i}><Link to={`/runs/${runId}/evidence/${encodeURIComponent(artifact)}`}>View evidence</Link></p> : null;
            }) : null}
            {typeof item.attempts === "number" && item.attempts > 1 ? <p>Tried {number(item.attempts)} times</p> : null}
            {Object.hasOwn(safetyClasses, text(item.safety_class) ?? "") ? <p>Safety class · {safetyClasses[text(item.safety_class)!]}</p> : null}
            {typeof item.occurrence_index === "number" && item.occurrence_index > 0 ? <p>Occurrence {number(item.occurrence_index)}</p> : null}
            {item.skill_replay ? <p>Replayed from a learned skill</p> : null}
            {itemJourney(item) ? <Link to={`/runs/${runId}/journeys/${itemJourney(item)}`}>Review recorded steps</Link> : null}
          </Disclosure>
        </li>)}</ul>
        {pages > 1 ? <div className="report-controls">
          <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous checks</button>
          <span aria-live="polite">Page {number(page + 1)} of {number(pages)}</span>
          <button type="button" disabled={page + 1 === pages} onClick={() => setPage(page + 1)}>Next checks</button>
        </div> : null}
      </>}
      {matchingJourneys.length ? <Disclosure label="Journeys">
        <ul className="report-rows">{matchingJourneys.map(journey => <li key={journey.id}><Disclosure label={<>
          <strong>{journey.mission_title}</strong> · {journey.persona_name} · {journey.persona_perspective} · <ReportStatus {...journeyOutcome(journey)} /> · {number(journey.step_count)} steps · {number(journey.artifact_count)} artifacts
        </>}>
          {journey.mission_objective ? <p>{journey.mission_objective}</p> : null}
          {journey.summary ? <p>{journey.summary}</p> : null}
          {journey.success_criteria?.length ? <ul>{journey.success_criteria.map(criterion => <li key={criterion}>{criterion}</li>)}</ul> : null}
          {records(journey.result?.criterion_evidence).map((item, index) => {
            const status = text(item.status) ?? "";
            const proof = { passed: "Satisfied", failed: "Not satisfied", unverified: "Not verified" };
            return <p key={index}>{text(item.criterion)} · {Object.hasOwn(proof, status) ? proof[status as keyof typeof proof] : "Not recorded"}{" "}
              {Array.isArray(item.evidence_step_ids) ? item.evidence_step_ids.map(step => typeof step === "number"
                ? <Link key={step} to={`/runs/${runId}/journeys/${journey.id}?step=${step}`}>View step {number(step)} </Link> : null) : null}
            </p>;
          })}
          {journey.error_message ? <p>{journey.error_message}</p> : null}
          {journey.attempt_number && journey.attempt_number > 1 ? <p>Attempt {number(journey.attempt_number)}</p> : null}
          {typeof journey.result?.human_wait_ms === "number" && journey.result.human_wait_ms > 0 ? <p>Waited {number(Math.round(journey.result.human_wait_ms / 1000))} seconds for a person</p> : null}
          {journey.evidence_available ? <Link to={`/runs/${runId}/journeys/${journey.id}`}>View evidence</Link> : null}
        </Disclosure></li>)}</ul>
      </Disclosure> : null}
    </section>}
  />;
}

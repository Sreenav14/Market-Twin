import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArtifactEvidence } from "../../components/markettwin/ArtifactEvidence";
import { JOURNEY_EXECUTION_STATUS } from "../../lib/status";
import { count, Disclosure, KeyFigures, number, record, records, ReportFrame, ReportStatus, text, Verdict } from "./ReportFrame";

export const observationReasons: Record<string, string> = {
  did_not_reproduce: "Did not happen again on re-check",
  replay_unavailable: "Could not be re-checked",
  authentication_required: "Needs a login",
  policy_blocked: "Blocked by the safety policy",
  testing_depth_budget: "Ran out of testing depth",
  unsupported_case_bounds_or_check: "This check is not supported yet",
  timed_out: "Timed out",
  time_budget: "Ran out of time",
  time_limit: "Reached the time limit",
};
const outcomes = {
  worked: { word: "Worked", tone: "works" },
  broken: { word: "Broken", tone: "broken" },
  could_not_check: { word: "Could not check", tone: "notchecked" },
  not_checked: { word: "Not checked", tone: "notchecked" },
} as const;
const caseWords = {
  passed: { word: "Passed", tone: "works" },
  failed: { word: "Failed", tone: "broken" },
  satisfied: { word: "Met", tone: "works" },
  not_satisfied: { word: "Not met", tone: "broken" },
  unverified: { word: "Not verified", tone: "notchecked" },
  not_run: { word: "Not run", tone: "notchecked" },
  inconclusive: { word: "Could not check", tone: "notchecked" },
  blocked: { word: "Blocked", tone: "notchecked" },
} as const;
const facts = {
  journeys_completed: "Journeys completed", journeys_attempted: "Journeys attempted", total_steps: "Total steps",
  failed_actions: "Failed actions", timeouts: "Timeouts", checks_passed: "Checks passed", checks_failed: "Checks failed",
};
const dimensions = { ease: "Ease", clarity: "Clarity", trust: "Trust", visual_quality: "Visual quality" };
const pageSize = 20;
const strings = (value: unknown) => Array.isArray(value) ? value.filter((value): value is string => typeof value === "string") : [];

/** Split a saved impression into its words and the machine metric tokens ([key=value]) it cites. */
export function splitMetrics(text: string): { clean: string; metrics: string[] } {
  const found: string[] = [];
  const clean = text.replace(/\[([a-z_]+)=([^\]]+)\]/g, (_match, key: string, value: string) => {
    found.push(`${key.replaceAll("_", " ")} ${value}`);
    return "";
  }).replace(/\s+([.,;])/g, "$1").replace(/\s{2,}/g, " ").trim();
  return { clean, metrics: [...new Set(found)] };
}

function EvidenceLinks({ runId, ids }: { runId: string; ids: unknown }) {
  return <>{strings(ids).map((id, index) => <Link key={id} to={`/runs/${runId}/evidence/${encodeURIComponent(id)}`}>View evidence{index ? ` ${index + 1}` : ""} </Link>)}</>;
}

export function ContractReport({ runId, payload, eyebrow, observations, first, ...frame }: {
  runId: string;
  payload: Record<string, unknown>;
  eyebrow?: ReactNode;
} & Pick<Parameters<typeof ReportFrame>[0], "rerunDiff" | "activity" | "first" | "observations" | "facts" | "technical">) {
  const [search] = useSearchParams();
  const [selection, setSelection] = useState<{ journey: unknown; tester: unknown }>();
  const [page, setPage] = useState(0);
  const verdict = record(payload.market_verdict);
  const coverage = record(payload.coverage);
  const journeys = records(payload.journeys);
  const cases = records(payload.cases);
  const whatWorks = strings(payload.what_works);
  const worksDetails = records(payload.what_works_details);
  const confirmed = records(payload.confirmed);
  const unverified = records(payload.unverified);
  const personas = records(record(payload.experience).personas);
  const testerIds = [...new Set(cases.map(item => item.persona_index))];
  const outcomeOf = (key: unknown) => {
    if (text(key) && whatWorks.includes(text(key)!)) return "worked";
    if (confirmed.some(item => item.journey_key === key)) return "broken";
    const runs = cases.filter(item => item.journey_key === key);
    return runs.length > 0 && runs.every(item => item.verdict === "not_run") ? "not_checked" : "could_not_check";
  };
  const journeyTitle = (key: unknown) => text(journeys.find(journey => journey.journey_key === key)?.title);
  const outcome = search.get("outcome");
  const filtered = journeys.filter(journey => (!outcome || !Object.hasOwn(outcomes, outcome) || outcomeOf(journey.journey_key) === outcome)
    && (!selection || selection.journey === journey.journey_key));
  const criteria = new Map<string, { check: string; journey: unknown }[]>();
  for (const journey of journeys) {
    for (const check of records(journey.checks)) {
      const id = text(check.assertion_id);
      const title = text(check.plain_language);
      if (id && title) criteria.set(id, [...(criteria.get(id) ?? []), { check: title, journey: journey.journey_key }]);
    }
  }
  const tested = count(coverage.tested_features);
  const discovered = count(coverage.discovered_features);
  const approved = count(verdict.journeys_approved);
  const executed = count(verdict.journeys_executed);
  const defects = count(verdict.confirmed_defects);
  const criterionRow = ([id, group]: [string, { check: string; journey: unknown }[]]) => {
    const matches = (item: Record<string, unknown>) => group.some(row => row.journey === item.journey_key && (item.assertion_id === id || item.check === row.check));
    const failure = confirmed.some(matches);
    const uncertain = unverified.find(matches) ?? unverified.find(item => group.some(row => row.journey === item.journey_key) && !item.assertion_id && !item.check);
    const passed = group.some(row => outcomeOf(row.journey) === "worked" || cases.some(item => item.journey_key === row.journey && ["passed", "satisfied"].includes(text(item.verdict) ?? "") && records(item.assertions).some(assertion => assertion.assertion_id === id)));
    return <li key={id}>{group[0].check} · <ReportStatus word={failure ? "Not met" : passed ? "Met" : "Can't tell"} tone={failure ? "broken" : passed ? "works" : "notchecked"} />
      {group.map(row => journeyTitle(row.journey)).filter(Boolean).map(title => <span key={title}> · on {title}</span>)}
      {!failure && !passed && uncertain ? <> · {observationReasons[text(uncertain.reason) ?? ""] ?? "Reason not recorded"}</> : null}
    </li>;
  };
  return <ReportFrame {...frame}
    takeaway={<>{eyebrow}<h2>Is it market-ready?</h2><Verdict value={verdict.verdict} kind="contract" />
      <KeyFigures figures={[
        { label: "Journeys approved", value: approved ?? "Not recorded" },
        { label: "Journeys executed", value: executed ?? "Not recorded" },
        { label: "Confirmed defects", value: defects ?? "Not recorded" },
      ]} />
    </>}
    first={first}
    middle={<section className="report-section"><h2>Frozen criteria</h2>
      {criteria.size ? <ul className="report-rows">{[...criteria].slice(0, pageSize).map(criterionRow)}</ul> : <p>No frozen criteria were recorded in this report.</p>}
      {criteria.size > pageSize ? <Disclosure label="More criteria"><ul className="report-rows">{[...criteria].slice(pageSize).map(criterionRow)}</ul></Disclosure> : null}
    </section>}
    coverage={<section className="report-section"><h2>Coverage</h2>
      {tested !== undefined && discovered !== undefined ? <p>Tested {tested} of {discovered} discovered features.</p> : <p>Feature coverage was not recorded in this report.</p>}
    </section>}
    observations={<>
      {confirmed.length ? <section className="report-section"><h2>Confirmed problems</h2><Disclosure label={`${number(confirmed.length)} confirmed problems`}>
        <ul className="report-rows">{confirmed.map((item, index) => <li key={index}>
          <Disclosure label={[text(item.check) ?? "Approved check failed", journeyTitle(item.journey_key)].filter(Boolean).join(" · ")}>
            <p>Reproduced on a fresh check (verification: verified deterministic).</p>
            {strings(item.screenshot_artifact_ids).map(id => <ArtifactEvidence key={id} runId={runId} artifactId={id} />)}
            <EvidenceLinks runId={runId} ids={item.artifact_ids} />
            {text(item.finding_id) ? <Link to={`/runs/${runId}/findings/${item.finding_id}`}>Inspect the confirmed problem</Link> : null}
          </Disclosure>
        </li>)}</ul>
      </Disclosure></section> : null}
      {unverified.length ? <section className="report-section"><h2>Unverified observations</h2><Disclosure label={`${number(unverified.length)} observations`}>
        <ul className="report-rows">{unverified.map((item, index) => <li key={index}>
          <Disclosure label={<>{text(item.check) ?? "Journey not confirmed"} · {journeyTitle(item.journey_key)} · {observationReasons[text(item.reason) ?? ""] ?? "Reason not recorded"}</>}>
            {count(item.completed_steps) !== undefined && count(item.planned_steps) !== undefined ? <p>Got through {count(item.completed_steps)} of {count(item.planned_steps)} steps.</p> : null}
            <EvidenceLinks runId={runId} ids={item.artifact_ids} />
          </Disclosure>
        </li>)}</ul>
      </Disclosure></section> : null}
      {observations}
      {personas.length ? <section className="report-section"><h2>How it felt</h2><Disclosure label="Tester impressions">
        <div className="report-cards">{personas.map((persona, index) => {
          const name = text(persona.name ?? persona.persona_name) ?? "Tester";
          const counts = record(persona.facts);
          const scores = record(persona.scores);
          const status = text(persona.status) ?? "";
          return <article key={index} className="tester-panel" aria-label={name}><h3>{name}</h3>
            <ReportStatus {...(Object.hasOwn(JOURNEY_EXECUTION_STATUS, status) ? JOURNEY_EXECUTION_STATUS[status] : { word: "Unavailable", tone: "notchecked" })} />
            <dl>{Object.entries(facts).map(([key, label]) => count(counts[key]) === undefined ? null : <div key={key}><dt>{label}</dt><dd>{count(counts[key])}</dd></div>)}</dl>
            {strings(counts.stuck_points).map(point => <p key={point}>Stuck at {point}</p>)}
            {Object.entries(dimensions).map(([key, label]) => {
              const justification = text(record(scores[key]).justification);
              if (!justification) return null;
              const parts = splitMetrics(justification);
              return <section key={key}><h4>{label}</h4><blockquote className="tester-quote voice-quote"><p>{parts.clean}</p><cite>— {name}, simulated tester</cite></blockquote>
                {parts.metrics.length ? <p className="tester-evidence-line">{parts.metrics.join(" · ")}</p> : null}
              </section>;
            })}
          </article>;
        })}</div>
      </Disclosure></section> : null}
    </>}
    inventory={<section className="report-section"><h2>Journeys</h2>
      {cases.length ? <Disclosure label="Tester by journey"><div className="report-matrix" tabIndex={0} aria-label="Tester by journey">
        <table><caption>Tester by journey</caption><thead><tr><th scope="col">Journey</th>{testerIds.map((id, index) => {
          const persona = personas.find(persona => persona.persona_index === id);
          return <th scope="col" key={index}>{text(persona?.name ?? persona?.persona_name) ?? `Tester ${index + 1}`}</th>;
        })}</tr></thead>
          <tbody>{journeys.map((journey, index) => <tr key={index}><th scope="row">{text(journey.title)}</th>{testerIds.map((id, tester) => {
            const matches = cases.filter(item => item.journey_key === journey.journey_key && item.persona_index === id);
            return <td key={tester}>{matches.length ? <button type="button" aria-pressed={selection?.journey === journey.journey_key && selection?.tester === id}
              onClick={() => { setPage(0); setSelection({ journey: journey.journey_key, tester: id }); }}>
              {matches.map((item, i) => <ReportStatus key={i} {...(Object.hasOwn(caseWords, text(item.verdict) ?? "") ? caseWords[item.verdict as keyof typeof caseWords] : { word: "Outcome unavailable", tone: "notchecked" })} />)}
            </button> : "—"}</td>;
          })}</tr>)}</tbody>
        </table>
      </div></Disclosure> : null}
      {selection ? <button type="button" onClick={() => { setSelection(undefined); setPage(0); }}>Clear filters</button> : null}
      <Disclosure label={`${number(filtered.length)} journeys`}>
        <ul className="report-rows">{filtered.slice(page * pageSize, (page + 1) * pageSize).map((journey, index) => {
          const key = journey.journey_key;
          const checks = records(journey.checks);
          const detail = worksDetails.find(item => item.journey_key === key);
          return <li key={text(key) ?? index}><Disclosure label={<>{text(journey.title) ?? "Approved journey"} · <ReportStatus {...outcomes[outcomeOf(key)]} /></>}>
            <ul>{checks.map((check, i) => <li key={i}>{text(check.plain_language)}</li>)}</ul>
            {cases.filter(item => item.journey_key === key && (!selection || item.persona_index === selection.tester)).flatMap(item => records(item.assertions)).map((item, i) =>
              <p key={i}>{text(item.plain_language)} <EvidenceLinks runId={runId} ids={item.artifact_ids} /></p>)}
            {detail ? records(detail.evidence).flatMap(item => records(item.assertions)).map((item, i) => <p key={i}><EvidenceLinks runId={runId} ids={item.artifact_ids} /></p>) : null}
          </Disclosure></li>;
        })}</ul>
        {filtered.length > pageSize ? <div className="report-controls">
          <button type="button" disabled={!page} onClick={() => setPage(page - 1)}>Previous journeys</button>
          <span aria-live="polite">Page {number(page + 1)} of {number(Math.ceil(filtered.length / pageSize))}</span>
          <button type="button" disabled={(page + 1) * pageSize >= filtered.length} onClick={() => setPage(page + 1)}>Next journeys</button>
        </div> : null}
      </Disclosure>
    </section>}
  />;
}

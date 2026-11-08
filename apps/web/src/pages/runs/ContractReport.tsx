import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { StatusPill } from "../../components/ui/StatusBadge";
import { CoverageProgress, JourneyMeter, StackedBar } from "../../components/markettwin/ResultFigures";
import { ArtifactEvidence } from "../../components/markettwin/ArtifactEvidence";

function object(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function rows(value: unknown): Record<string, unknown>[] { return Array.isArray(value) ? value.map(object) : []; }
function string(value: unknown, fallback = "Unavailable") { return typeof value === "string" ? value : fallback; }
function count(value: unknown) { return typeof value === "number" ? value : "unavailable"; }
function num(value: unknown): number | null { return typeof value === "number" && Number.isFinite(value) ? value : null; }
function strings(value: unknown): string[] { return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []; }
function observationReason(item: Record<string, unknown>) {
  const reasons: Record<string, string> = { did_not_reproduce: "did not happen again on re-check", replay_unavailable: "could not be re-checked", authentication_required: "needs a login", policy_blocked: "was blocked by the app's access rules", testing_depth_budget: "was outside the selected testing depth", unsupported_case_bounds_or_check: "could not be run with the available checks" };
  if (["timed_out", "time_budget", "time_limit"].includes(string(item.reason))) return `ran out of time at step ${count(item.completed_steps)} of ${count(item.planned_steps)}`;
  return reasons[string(item.reason)] || "could not be confirmed";
}
function EvidenceLinks({ runId, item }: { runId: string; item: Record<string, unknown> }) {
  return <>{strings(item.artifact_ids).map(id => <Link key={id} className="text-link" to={`/runs/${runId}/evidence/${id}`}>View check evidence</Link>)}</>;
}

type JourneyOutcome = "worked" | "broken" | "could_not_check" | "not_checked";
const OUTCOME_WORDS: Record<JourneyOutcome, string> = { worked: "Worked", broken: "Broken", could_not_check: "Could not check", not_checked: "Not checked" };
const OUTCOME_VERBS: Record<JourneyOutcome, string> = { worked: "worked", broken: "broke", could_not_check: "could not be checked", not_checked: "were not checked" };
const TESTER_COLOURS = ["var(--tom)", "var(--maya)", "var(--priya)", "var(--tester-4)", "var(--tester-5)", "var(--tester-6)"];

/** Split a saved impression into its words and the machine metric tokens ([key=value]) it cites. */
export function splitMetrics(text: string): { clean: string; metrics: string[] } {
  const found: string[] = [];
  const clean = text.replace(/\[([a-z_]+)=([^\]]+)\]/g, (_match, key: string, value: string) => {
    found.push(`${key.replaceAll("_", " ")} ${value}`);
    return "";
  }).replace(/\s+([.,;])/g, "$1").replace(/\s{2,}/g, " ").trim();
  return { clean, metrics: [...new Set(found)] };
}

export function ContractReport({ runId, payload }: { runId: string; payload: Record<string, unknown> }) {
  // Home's outcome bar deep-links here with ?outcome=<key>; the filter
  // starts there and stays fully user-controlled afterwards.
  const [searchParams] = useSearchParams();
  const initialOutcome = searchParams.get("outcome");
  const [outcomeFilter, setOutcomeFilter] = useState<JourneyOutcome | null>(
    initialOutcome === "worked" || initialOutcome === "broken" || initialOutcome === "could_not_check" || initialOutcome === "not_checked"
      ? initialOutcome : null,
  );
  const coverage = object(payload.coverage);
  const verdict = object(payload.market_verdict);
  const personas = rows(object(payload.experience).personas);
  const journeys = rows(payload.journeys);
  const cases = rows(payload.cases);
  const titles: Record<string, string> = {};
  for (const journey of journeys) titles[string(journey.journey_key)] = string(journey.title);
  const works = strings(payload.what_works);
  const worksDetails = rows(payload.what_works_details);
  const confirmed = rows(payload.confirmed);
  const unverified = rows(payload.unverified);
  const verdictLabels: Record<string, string> = { ready: "Ready", ready_with_issues: "Ready with issues", not_ready: "Not ready yet", insufficient_evidence: "Can't tell yet" };
  const verdictTones: Record<string, "works" | "couldnot" | "broken" | "notchecked"> = { ready: "works", ready_with_issues: "couldnot", not_ready: "broken", insufficient_evidence: "notchecked" };
  const verdictWord = verdictLabels[string(verdict.verdict)] || "Verdict unavailable";
  const verdictTone = verdictTones[string(verdict.verdict)] || "notchecked";
  const confirmedCount = num(verdict.confirmed_defects) ?? confirmed.length;
  const testedFeatures = num(coverage.tested_features);
  const discoveredFeatures = num(coverage.discovered_features);

  // Per-journey outcomes, derived only from what the payload records.
  const executedKeys = new Set(cases.filter(c => c.verdict !== "not_run").map(c => string(c.journey_key)));
  const hasCases = Array.isArray(payload.cases);
  const confirmedKeys = new Set(confirmed.map(item => string(item.journey_key)));
  const outcomeOf = (journey: Record<string, unknown>): JourneyOutcome => {
    const key = string(journey.journey_key);
    if (works.includes(key)) return "worked";
    if (confirmedKeys.has(key)) return "broken";
    if (hasCases && !executedKeys.has(key)) return "not_checked";
    return "could_not_check";
  };
  const outcomeCounts: Record<JourneyOutcome, number> = { worked: 0, broken: 0, could_not_check: 0, not_checked: 0 };
  for (const journey of journeys) outcomeCounts[outcomeOf(journey)] += 1;
  const testersTotal = new Set(cases.map(c => c.persona_index)).size;
  const testersRan = (key: string) => new Set(cases.filter(c => string(c.journey_key) === key && c.verdict !== "not_run").map(c => c.persona_index)).size;

  // Coverage: name the untested remainder where the payload lets us.
  const testedFeatureKeys = new Set(journeys.filter(j => executedKeys.has(string(j.journey_key))).map(j => string(j.feature_key)));
  const notTestedJourneys = journeys.filter(j => !testedFeatureKeys.has(string(j.feature_key)));
  const notTestedFeatures = [...new Set(notTestedJourneys.map(j => string(j.feature_key)))];
  const anonymousRemainder = testedFeatures !== null && discoveredFeatures !== null && journeys.length > 0
    ? Math.max(0, discoveredFeatures - testedFeatures - notTestedFeatures.length) : 0;
  const coverageTitle = testedFeatures === null || discoveredFeatures === null
    ? "Coverage"
    : testedFeatures === 0
      ? `Nothing was tested — 0 of ${discoveredFeatures} features`
      : testedFeatures * 2 <= discoveredFeatures
        ? `Most of the app was not reached — ${discoveredFeatures - testedFeatures} of ${discoveredFeatures} features unchecked`
        : `Tested ${testedFeatures} of ${discoveredFeatures} features — ${discoveredFeatures - testedFeatures} unchecked`;

  const outcomeTitle = outcomeCounts.broken > 0
    ? `Problems confirmed in ${outcomeCounts.broken} of ${journeys.length} ${journeys.length === 1 ? "journey" : "journeys"}`
    : outcomeCounts.could_not_check + outcomeCounts.not_checked > 0
      ? `No breaks confirmed — ${outcomeCounts.could_not_check + outcomeCounts.not_checked} of ${journeys.length} journeys could not be fully checked`
      : "Every journey worked";
  const SECTION_FILTERS: Record<"works" | "broken" | "unverified", JourneyOutcome[]> = {
    works: ["worked"], broken: ["broken"], unverified: ["could_not_check", "not_checked"],
  };
  const showSection = (section: "works" | "broken" | "unverified") =>
    !outcomeFilter || SECTION_FILTERS[section].includes(outcomeFilter);

  // Tester panels: identical layout and measures (small multiples), most-blocked first when the data allows the order.
  const personaOrder = personas.map((persona, index) => ({ persona, index }));
  const allCounted = personaOrder.every(({ persona }) => num(object(persona.facts).journeys_completed) !== null);
  if (allCounted && personaOrder.length > 1) {
    personaOrder.sort((a, b) =>
      (num(object(a.persona.facts).journeys_completed) ?? 0) - (num(object(b.persona.facts).journeys_completed) ?? 0)
      || (num(a.persona.persona_index) ?? a.index) - (num(b.persona.persona_index) ?? b.index));
  }

  return <article className="contract-report">
    <section className={`panel contract-verdict verdict-tone-${verdictTone}`} aria-labelledby="contract-market">
      <h2 id="contract-market">Is it market-ready?</h2>
      <p className="contract-verdict-word">{verdictWord}</p>
      <p>Tested {count(verdict.journeys_executed)} of {count(verdict.journeys_approved)} approved journeys · {count(verdict.confirmed_defects)} confirmed {num(verdict.confirmed_defects) === 1 ? "problem" : "problems"}.</p>
      {verdict.verdict === "insufficient_evidence" ? <p>Too little of the approved work was tested, or fewer than two testers completed a journey. Review the unconfirmed observations and coverage before making a release decision.</p> : null}
      {coverage.approved === 0 ? <p>No approved tests — nothing was verified.</p> : null}
      <dl className="contract-verdict-figures">
        <div><dt>Confirmed problems</dt><dd>{confirmedCount}</dd></div>
        {testedFeatures !== null && discoveredFeatures !== null ? <div><dt>Features tested</dt><dd>{testedFeatures} of {discoveredFeatures}</dd></div> : null}
        {num(verdict.journeys_executed) !== null && num(verdict.journeys_approved) !== null ? <div><dt>Journeys tested</dt><dd>{num(verdict.journeys_executed)} of {num(verdict.journeys_approved)}</dd></div> : null}
      </dl>
    </section>

    <section className="panel" aria-labelledby="contract-coverage-title">
      <h2 id="contract-coverage-title">{coverageTitle}</h2>
      <p className="contract-coverage" role="status">Coverage: tested {count(coverage.tested_features)} of {count(coverage.discovered_features)} discovered features.</p>
      {testedFeatures !== null && discoveredFeatures !== null && discoveredFeatures > 0 ? <CoverageProgress tested={testedFeatures} discovered={discoveredFeatures} /> : null}
      {hasCases && notTestedJourneys.length ? <p className="rf-named-remainder">Not tested: {notTestedJourneys.map(j => `${string(j.title)} (${string(j.feature_key).replaceAll("_", " ")})`).join("; ")}.</p> : null}
      {anonymousRemainder > 0 ? <p className="rf-named-remainder">Plus {anonymousRemainder} more discovered {anonymousRemainder === 1 ? "feature" : "features"} that no approved test covers.</p> : null}
    </section>

    {journeys.length ? <section className="panel" aria-labelledby="contract-outcomes-title">
      <h2 id="contract-outcomes-title">{outcomeTitle}</h2>
      <p className="rf-subtitle">Of {journeys.length} journeys: {outcomeCounts.worked} worked, {outcomeCounts.broken} broke, {outcomeCounts.could_not_check} could not be checked{outcomeCounts.not_checked ? `, ${outcomeCounts.not_checked} not checked` : ""}.</p>
      <StackedBar
        total={journeys.length}
        unit="journeys"
        selected={outcomeFilter}
        onSelect={(key) => setOutcomeFilter(key as JourneyOutcome | null)}
        segments={[
          { key: "worked", word: OUTCOME_WORDS.worked, count: outcomeCounts.worked, tone: "works" },
          { key: "broken", word: OUTCOME_WORDS.broken, count: outcomeCounts.broken, tone: "broken" },
          { key: "could_not_check", word: OUTCOME_WORDS.could_not_check, count: outcomeCounts.could_not_check, tone: "couldnot" },
          ...(outcomeCounts.not_checked ? [{ key: "not_checked", word: OUTCOME_WORDS.not_checked, count: outcomeCounts.not_checked, tone: "notchecked" as const }] : []),
        ]}
      />
      {outcomeFilter ? <p className="rf-filter-note" role="status">
        Showing only journeys that {OUTCOME_VERBS[outcomeFilter]} — {outcomeCounts[outcomeFilter]} of {journeys.length} journeys, and their findings below.{" "}
        <button type="button" className="text-link rf-clear-filter" onClick={() => setOutcomeFilter(null)}>Clear filter</button>
      </p> : null}
      <ul className="rf-journey-rows">
        {journeys.filter(j => !outcomeFilter || outcomeOf(j) === outcomeFilter).map(journey => {
          const key = string(journey.journey_key);
          const outcome = outcomeOf(journey);
          return <li key={key} className="rf-journey-row">
            <span className="rf-journey-name">{string(journey.title)}</span>
            <span className="rf-journey-meta">
              {rows(journey.checks).length} {rows(journey.checks).length === 1 ? "check" : "checks"}
              {hasCases && testersTotal > 0 ? <> · ran by {testersRan(key)} of {testersTotal} testers</> : null}
            </span>
            <StatusPill tone={outcome === "worked" ? "success" : outcome === "broken" ? "danger" : outcome === "could_not_check" ? "warning" : "neutral"} glyph={outcome === "worked" ? "✓" : outcome === "broken" ? "×" : outcome === "could_not_check" ? "?" : "–"} size="sm">{OUTCOME_WORDS[outcome]}</StatusPill>
          </li>;
        })}
      </ul>
    </section> : null}

    {showSection("works") ? <section className="panel" aria-labelledby="contract-works"><h2 id="contract-works"><span aria-hidden="true">✓ </span>What works</h2>
      <p className="rf-group-definition">Journeys where every tester completed every check.</p>
      {works.length ? <ul>{works.map(key => {
        const detail = worksDetails.find(d => d.journey_key === key);
        const checks: Record<string, unknown>[] = detail ? rows(detail.checks).map(check => ({ ...check, artifact_ids: rows(detail.evidence).flatMap(e => rows(e.assertions)).filter(a => a.assertion_id === check.assertion_id).flatMap(a => strings(a.artifact_ids)) })) : rows(payload.cases).filter(c => c.journey_key === key).flatMap(c => rows(c.assertions));
        return <li key={key}><h3>{detail ? string(detail.title, titles[key] || key.replaceAll("_", " ")) : titles[key] || key.replaceAll("_", " ")}</h3><ul>{checks.map((check, i) => <li key={i}>{string(check.plain_language, "Approved check passed")} <EvidenceLinks runId={runId} item={check} /></li>)}</ul></li>;
      })}</ul> : <p>No journeys have been shown to pass all their checks.</p>}
    </section> : null}
    {showSection("broken") ? <section className="panel" aria-labelledby="contract-broken"><h2 id="contract-broken"><span aria-hidden="true">✕ </span>What&apos;s broken</h2>
      <p className="rf-group-definition">{confirmed.length} confirmed {confirmed.length === 1 ? "problem" : "problems"} — each was seen again on re-check in a fresh browser before it counted here.</p>
      {confirmed.length ? <ul>{confirmed.map((item, index) => <li key={`${string(item.finding_id)}-${index}`}>
        <h3>Failed: {string(item.check, "Approved check failed")}</h3>
        {titles[string(item.journey_key)] ? <p className="rf-journey-meta">{titles[string(item.journey_key)]}</p> : null}
        <p><StatusPill tone="danger" glyph="×">Failed again on re-check</StatusPill></p>
        {strings(item.screenshot_artifact_ids)[0] ? <ArtifactEvidence runId={runId} artifactId={strings(item.screenshot_artifact_ids)[0]} autoLoad /> : <EvidenceLinks runId={runId} item={item} />}
        {typeof item.finding_id === "string" ? <Link to={`/runs/${runId}/findings/${item.finding_id}`}>Inspect the confirmed problem</Link> : null}
      </li>)}</ul> : <p>No confirmed problems were found in the approved tests.</p>}
    </section> : null}
    {showSection("unverified") ? <section className="panel" aria-labelledby="contract-unconfirmed"><h3 id="contract-unconfirmed">Seen once — not confirmed</h3>
      <p className="rf-group-definition">{unverified.length} seen once — not reproduced or not re-checkable, so not counted as confirmed problems.</p>
      {unverified.length ? <ul>{unverified.map((item, index) => <li key={index}><p><span className="rf-badge-outline">Seen once</span> {string(item.check, titles[string(item.journey_key)] || "Journey not confirmed")} — {observationReason(item)}.</p><EvidenceLinks runId={runId} item={item} /></li>)}</ul> : <p>No unconfirmed observations were recorded.</p>}
    </section> : null}
    <section className="panel contract-feeling-band" aria-labelledby="contract-feeling"><h2 id="contract-feeling">How it felt</h2>
      <p className="rf-group-definition">Impressions from the simulated testers, in their own words. They never change the verdict above.</p>
      {personas.length && allCounted && personaOrder.length > 1 ? <p className="rf-subtitle">One panel per tester, the same measures in each; ordered with the most-blocked tester first.</p> : null}
      {personas.length ? <div className="tester-grid">{personaOrder.map(({ persona, index }) => {
        const facts = object(persona.facts), scores = object(persona.scores);
        const name = string(persona.name ?? persona.persona_name, "Tester");
        const personaIndex = num(persona.persona_index) ?? index;
        const completed = num(facts.journeys_completed), attempted = num(facts.journeys_attempted);
        return <section key={index} className="tester-panel" aria-label={name}>
          <h3 className="tester-panel-name"><span className="tester-chip" style={{ background: TESTER_COLOURS[personaIndex % TESTER_COLOURS.length] }} aria-hidden="true" />{name}</h3>
          <p className="tester-panel-role">Simulated tester</p>
          {completed !== null && attempted !== null && attempted > 0 ? <JourneyMeter completed={completed} attempted={attempted} /> : null}
          <p>Completed {count(facts.journeys_completed)} of {count(facts.journeys_attempted)} journeys · {count(facts.total_steps)} steps · {count(facts.failed_actions)} failed actions · {count(facts.timeouts)} timeouts.</p>
          {num(facts.checks_passed) !== null ? <p className="rf-journey-meta">Checks passed {count(facts.checks_passed)} · Checks failed {count(facts.checks_failed)}</p> : null}
          {Array.isArray(facts.stuck_points) && facts.stuck_points.length ? <p>Stuck at: {facts.stuck_points.map(String).join(", ")}</p> : null}
          {persona.status === "completed" ? <dl>{["ease", "clarity", "trust", "visual_quality"].map(dimension => {
            const score = object(scores[dimension]);
            const justification = typeof score.justification === "string" && score.justification.trim() ? splitMetrics(score.justification) : null;
            return <div key={dimension}><dt>{dimension.replaceAll("_", " ")}</dt><dd>{justification ? <>
              <blockquote className="tester-quote voice-quote"><p>{justification.clean}</p><cite>— {name}, simulated tester</cite></blockquote>
              {justification.metrics.length ? <p className="tester-evidence-line">Evidence · {justification.metrics.join(" · ")}</p> : null}
            </> : "Unavailable — no supported assessment"}</dd></div>;
          })}</dl> : <p>Experience assessment unavailable. The recorded activity above is still available.</p>}
        </section>;
      })}</div> : <p>Experience assessment is unavailable.</p>}
    </section>
  </article>;
}

import { Link } from "react-router-dom";
import { ArtifactEvidence } from "./FindingDetailPage";

function object(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function rows(value: unknown): Record<string, unknown>[] { return Array.isArray(value) ? value.map(object) : []; }
function string(value: unknown, fallback = "Unavailable") { return typeof value === "string" ? value : fallback; }
function count(value: unknown) { return typeof value === "number" ? value : "unavailable"; }
function strings(value: unknown): string[] { return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []; }
function scoreLabel(dimension: string, score: number) {
  if (dimension === "ease") return score <= 2 ? "Hard" : score === 3 ? "Okay" : "Easy";
  if (dimension === "clarity") return score <= 2 ? "Confusing" : score === 3 ? "Okay" : "Clear";
  if (dimension === "trust") return score <= 2 ? "Unreliable" : score === 3 ? "Okay" : "Reliable";
  return score <= 2 ? "Unfinished" : score === 3 ? "Okay" : "Polished";
}
function observationReason(item: Record<string, unknown>) {
  const reasons: Record<string, string> = { did_not_reproduce: "did not happen again on re-check", replay_unavailable: "could not be re-checked", authentication_required: "needs a login", policy_blocked: "was blocked by the app's access rules", testing_depth_budget: "was outside the selected testing depth", unsupported_case_bounds_or_check: "could not be run with the available checks" };
  if (["timed_out", "time_budget", "time_limit"].includes(string(item.reason))) return `ran out of time at step ${count(item.completed_steps)} of ${count(item.planned_steps)}`;
  return reasons[string(item.reason)] || "could not be confirmed";
}
function EvidenceLinks({ runId, item }: { runId: string; item: Record<string, unknown> }) {
  return <>{strings(item.artifact_ids).map(id => <Link key={id} className="text-link" to={`/runs/${runId}/evidence/${id}`}>View check evidence</Link>)}</>;
}

export function ContractReport({ runId, payload }: { runId: string; payload: Record<string, unknown> }) {
  const coverage = object(payload.coverage);
  const verdict = object(payload.market_verdict);
  const personas = rows(object(payload.experience).personas);
  const means = object(verdict.persona_means);
  const titles: Record<string, string> = {};
  for (const journey of rows(payload.journeys)) titles[string(journey.journey_key)] = string(journey.title);
  const works = strings(payload.what_works);
  const worksDetails = rows(payload.what_works_details);
  const verdictLabels: Record<string, string> = { ready: "Ready", ready_with_issues: "Ready with issues", not_ready: "Not ready", insufficient_evidence: "Insufficient evidence" };
  return <article className="contract-report">
    <p className="panel contract-coverage" role="status">Coverage: tested {count(coverage.tested_features)} of {count(coverage.discovered_features)} discovered features.</p>
    <section className="panel" aria-labelledby="contract-works"><h2 id="contract-works">What works</h2>
      {works.length ? <ul>{works.map(key => {
        const detail = worksDetails.find(d => d.journey_key === key);
        const checks: Record<string, unknown>[] = detail ? rows(detail.checks).map(check => ({ ...check, artifact_ids: rows(detail.evidence).flatMap(e => rows(e.assertions)).filter(a => a.assertion_id === check.assertion_id).flatMap(a => strings(a.artifact_ids)) })) : rows(payload.cases).filter(c => c.journey_key === key).flatMap(c => rows(c.assertions));
        return <li key={key}><h3>{detail ? string(detail.title, titles[key] || key.replaceAll("_", " ")) : titles[key] || key.replaceAll("_", " ")}</h3><ul>{checks.map((check, i) => <li key={i}>{string(check.plain_language, "Approved check passed")} <EvidenceLinks runId={runId} item={check} /></li>)}</ul></li>;
      })}</ul> : <p>No journeys have been shown to pass all their checks.</p>}
    </section>
    <section className="panel" aria-labelledby="contract-broken"><h2 id="contract-broken">What&apos;s broken</h2>
      {rows(payload.confirmed).length ? <ul>{rows(payload.confirmed).map((item, index) => <li key={`${string(item.finding_id)}-${index}`}>
        <h3>{string(item.check, "Approved check failed")}</h3><p>Failed again on re-check.</p>
        {strings(item.screenshot_artifact_ids)[0] ? <ArtifactEvidence runId={runId} artifactId={strings(item.screenshot_artifact_ids)[0]} autoLoad /> : <EvidenceLinks runId={runId} item={item} />}
        {typeof item.finding_id === "string" ? <Link to={`/runs/${runId}/findings/${item.finding_id}`}>Inspect the confirmed problem</Link> : null}
      </li>)}</ul> : <p>No confirmed problems were found in the approved tests.</p>}
    </section>
    <section className="panel" aria-labelledby="contract-unconfirmed"><h3 id="contract-unconfirmed">Seen once — not confirmed</h3>
      {rows(payload.unverified).length ? <ul>{rows(payload.unverified).map((item, index) => <li key={index}><p>{string(item.check, titles[string(item.journey_key)] || "Journey not verified")} — {observationReason(item)}.</p><EvidenceLinks runId={runId} item={item} /></li>)}</ul> : <p>No unconfirmed observations were recorded.</p>}
    </section>
    <section className="panel" aria-labelledby="contract-feeling"><h2 id="contract-feeling">How it felt</h2>
      {personas.length ? personas.map((persona, index) => {
        const facts = object(persona.facts), scores = object(persona.scores);
        return <section key={index} aria-label={string(persona.persona_name, "Tester")}><h3>{string(persona.persona_name, "Tester")}</h3>
          <p>Completed {count(facts.journeys_completed)} of {count(facts.journeys_attempted)} journeys · {count(facts.total_steps)} steps · {count(facts.failed_actions)} failed actions · {count(facts.timeouts)} timeouts.</p>
          {Array.isArray(facts.stuck_points) && facts.stuck_points.length ? <p>Stuck at: {facts.stuck_points.map(String).join(", ")}</p> : null}
          {persona.status === "completed" ? <dl>{["ease", "clarity", "trust", "visual_quality"].map(dimension => {
            const score = object(scores[dimension]);
            return <div key={dimension}><dt>{dimension.replaceAll("_", " ")}</dt><dd>{typeof score.score === "number" ? <><strong>{scoreLabel(dimension, score.score)} ({score.score}/5)</strong><p>{string(score.justification)}</p></> : "Unavailable — no supported assessment"}</dd></div>;
          })}</dl> : <p>Experience assessment unavailable. The recorded activity above is still available.</p>}
        </section>;
      }) : <p>Experience assessment is unavailable.</p>}
    </section>
    <section className="panel" aria-labelledby="contract-market"><h2 id="contract-market">Is it market-ready?</h2>
      <h3>{verdictLabels[string(verdict.verdict)] || "Verdict unavailable"}</h3>
      <p>Tested {count(verdict.journeys_executed)} of {count(verdict.journeys_approved)} approved journeys · {count(verdict.confirmed_defects)} confirmed problems · Tester scores: {Object.entries(means).length ? Object.entries(means).map(([name, mean]) => `${name} ${typeof mean === "number" ? mean.toFixed(1) : "unavailable"}`).join(", ") : "unavailable"}.</p>
      {verdict.verdict === "insufficient_evidence" ? <p>Too little of the approved work was tested, or fewer than two testers completed a journey. Review the unconfirmed observations and coverage before making a release decision.</p> : null}
      {coverage.approved === 0 ? <p>No approved tests — nothing was verified.</p> : null}
    </section>
  </article>;
}

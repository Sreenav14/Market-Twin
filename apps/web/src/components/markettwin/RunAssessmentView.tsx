import { Link } from "react-router-dom";
import { StatusBadge } from "../ui/StatusBadge";

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}
function outcome(value: unknown) {
  return value === "met" ? "passed" : value === "not_met" ? "failed" : value === "partially_met" ? "partial" : "inconclusive";
}

export function RunAssessmentView({ assessment, runId }: { assessment: unknown; runId: string }) {
  const result = object(assessment);
  const overall = object(result.overall);
  const individual = Array.isArray(result.individual_results) ? result.individual_results.map(object) : [];
  const runtime = object(result.runtime);
  return <section id="report-assessment" className="run-assessment" aria-labelledby="assessment-heading">
    <h3 id="assessment-heading">Overall assessment</h3>
    {result.status !== "completed" ? <p className="inline-note">{result.status === "unavailable" && typeof result.reason === "string" ? result.reason : "An overall model assessment was not recorded for this report version. Saved journey results and evidence checks remain available."}</p> : <>
      <div className="run-record-badges"><span>Testing goal <StatusBadge status={outcome(overall.goal_outcome)} /></span><span>Ease of use: {typeof overall.ease_of_use === "string" ? overall.ease_of_use : "inconclusive"}</span></div>
      <p>{typeof overall.summary === "string" ? overall.summary : "No overall summary recorded."}</p>
      {strings(overall.recommendations).length ? <><h4>Recommendations</h4><ul>{strings(overall.recommendations).map((item, index) => <li key={index}>{item}</li>)}</ul></> : null}
      <h4>Scope and limitations</h4><ul>{strings(overall.limitations).map((item, index) => <li key={index}>{item}</li>)}</ul>
      <div className="run-evidence-links">{strings(overall.supporting_journey_ids).map((id) => <Link className="text-link" key={id} to={`/runs/${runId}/journeys#journey-${id}`}>Supporting journey {id.slice(0, 8)}</Link>)}</div>
      <details className="run-assessment-details"><summary>Individual journey evaluations · {individual.length}</summary><div className="run-records">{individual.map((item, index) => <article className="panel run-record" key={index}>
        <div className="section-heading"><h4>{typeof item.persona_name === "string" && typeof item.mission_title === "string" ? `${item.persona_name} · ${item.mission_title}` : typeof item.journey_id === "string" ? `Journey ${item.journey_id.slice(0, 8)}` : "Recorded journey"}</h4><StatusBadge status={outcome(item.goal_outcome)} /></div>
        <p>{typeof item.summary === "string" ? item.summary : "No summary recorded."}</p>
        <p className="muted">Ease of use: {typeof item.ease_of_use === "string" ? item.ease_of_use : "inconclusive"}</p>
        <ul>{strings(item.recommendations).map((recommendation, itemIndex) => <li key={itemIndex}>{recommendation}</li>)}</ul>
        {typeof item.journey_id === "string" ? <Link className="text-link" to={`/runs/${runId}/journeys#journey-${item.journey_id}`}>Inspect recorded journey</Link> : null}
      </article>)}</div></details>
      <p className="muted">Model assessment of recorded test evidence{typeof runtime.model_name === "string" ? ` · ${runtime.model_name}` : ""}{typeof runtime.duration_seconds === "number" ? ` · ${runtime.duration_seconds.toFixed(1)} seconds` : ""}. This is not a guarantee about untested application flows.</p>
    </>}
  </section>;
}

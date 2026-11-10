import { Link } from "react-router-dom";

const labels: Record<string, string> = {
  worked: "Worked", broken: "Broken", could_not_check: "Could not check",
  not_checked: "Not checked", blocked: "Blocked", needs_human_login: "Needs human action",
  pending: "Not checked", running: "Incomplete",
  owner_disabled: "Disabled by owner",
};

export function HarnessReport({ runId, payload }: { runId: string; payload: Record<string, unknown> }) {
  const board = payload.board && typeof payload.board === "object" ? payload.board as Record<string, unknown> : {};
  const coverage = board.coverage && typeof board.coverage === "object" ? board.coverage as Record<string, unknown> : {};
  const items = Array.isArray(payload.items) ? payload.items.filter(
    (item): item is Record<string, unknown> => !!item && typeof item === "object" && !Array.isArray(item),
  ) : [];
  return <section className="panel" aria-labelledby="harness-results-title">
    <h2 id="harness-results-title">{typeof payload.verdict === "string" ? payload.verdict : "Can't tell yet"}</h2>
    {typeof coverage.checked === "number" && typeof coverage.total_items === "number" ?
      <p>Checked {coverage.checked} of {coverage.total_items} discovered items. {typeof coverage.denominator === "number" ? `${coverage.denominator} were eligible after owner exclusions.` : ""} This verdict applies only to the recorded scope.</p> :
      <p>{items.length} checks were recorded. Coverage is not available.</p>}
    {items.length === 0 ? <p>No checks were recorded for this test, so there are no results to assess.</p> :
      <ul>{items.map((item, index) => {
        const status = typeof item.status === "string" ? item.status : "unknown";
        return <li key={index}>
          <strong>{typeof item.name === "string" ? item.name : "Unnamed check"}</strong>{" — "}
          {labels[status] ?? "Unknown outcome"}
          {typeof item.reason === "string" && item.reason ? <> · {item.reason.replaceAll("_", " ")}</> : null}
          {typeof item.journey_id === "string" ? <> · <Link to={`/runs/${runId}/journeys/${item.journey_id}`}>Review recorded steps</Link></> : null}
        </li>;
      })}</ul>}
  </section>;
}

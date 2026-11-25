import type { AppMapFreshnessBlock } from "./AppMapPanel";

// Phase 4 (doc 23 section 13 item 28): the freshness line. A map no
// preflight has ever swept reads "not checked yet" — the measured
// state 'unknown' is never dressed up as 'current'.
function freshnessText(freshness: AppMapFreshnessBlock): string {
  if (!freshness || freshness.state === "unknown" || !freshness.last_preflight_at) {
    return "not checked yet";
  }
  const counts = freshness.outcome_counts ?? {};
  const at = new Date(freshness.last_preflight_at).toLocaleString();
  return (
    `${freshness.state} · last preflight ${at} · ` +
    `${counts.present ?? 0} present · ${counts.changed ?? 0} changed · ` +
    `${counts.unreachable ?? 0} unreachable · ${counts.missing ?? 0} missing · ` +
    `${counts.new ?? 0} new`
  );
}

export function AppMapFreshness({ freshness }: { freshness: AppMapFreshnessBlock }) {
  return <div><dt id="app-map-freshness">Freshness</dt><dd>{freshnessText(freshness)}</dd></div>;
}

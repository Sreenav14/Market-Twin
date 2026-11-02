import type { RunPreflight } from "../../lib/api";

export function RunPreflightPanel({ data, error, loading, onRefresh }: { data?: RunPreflight; error?: string | null; loading: boolean; onRefresh: () => void }) {
  return <section className="panel" aria-label="Test readiness"><h3>Ready to test?</h3>
    {loading ? <p role="status">Checking the test runner and report writer…</p> : error ? <p role="alert">{error}</p> : data?.ready ? <p>The test runner and report writer are ready.</p> : <ul>{data?.checks.filter(check => !check.ready).map(check => <li key={check.name}>{check.reason || "A required service is unavailable."}</li>)}</ul>}
    <button type="button" className="secondary-button compact" disabled={loading} onClick={onRefresh}>Check again</button>
  </section>;
}

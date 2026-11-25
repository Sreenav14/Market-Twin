import { InlineAlert } from "../ui/Feedback";
import type { RunPreflight } from "../../lib/api";

export function RunPreflightPanel({ data, error, loading, onRefresh }: { data?: RunPreflight; error?: string | null; loading: boolean; onRefresh: () => void }) {
  const blockingChecks = data?.checks.filter((check) => !check.ready && !check.advisory) ?? [];
  const preparation = data?.checks.find((check) => check.name === "app_map");
  const advisories = data?.checks.filter((check) => check.advisory) ?? [];
  return (
    <section className="panel" aria-label="Test readiness">
      <h3>Ready to test?</h3>
      {error ? <InlineAlert severity="error" title={error} role="alert" /> : null}
      {loading && !data ? <p role="status">Checking test readiness?</p> : null}
      {data?.ready ? <p>The test runner and report writer are ready.</p> : null}
      {blockingChecks.length ? (
        <ul aria-live="polite">
          {blockingChecks.map((check) => <li key={check.name}>{check.reason || "A required service is unavailable."}</li>)}
        </ul>
      ) : null}
      {preparation?.ready && !preparation.advisory ? <p role="status">{preparation.reason}</p> : null}
      {advisories.map((check) => <p key={check.name}>{check.reason}</p>)}
      <button type="button" className="secondary-button compact" disabled={loading} onClick={onRefresh}>Check again</button>
    </section>
  );
}

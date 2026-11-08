/**
 * Slop report (U-P6-05): three family numbers, never blended.
 * Slop gets its derived percentage (or the honest suppression
 * headline) with its counts always beside it; defects are counts
 * with severities; effort explains itself when no task was
 * performed. There is no verdict here — readiness comes only from
 * an Explore & Test run.
 */

export interface SlopReportPayload {
  run_kind?: string;
  families?: {
    slop: {
      headline: string;
      percentage: number | null;
      judged: number;
      severe: number;
      minor: number;
      clean: number;
      cant_tell: number;
      coverage: number;
      page_signals: Array<{ rule_id: string; severity: string; detail: string }>;
    };
    defects: {
      serious: number;
      minor: number;
      per_rule: Array<{
        rule_id: string;
        name: string;
        severity: string;
        occurrences: number;
        pages: string[];
      }>;
    };
    effort: { value: number | null; reason?: string };
    states_visited: number;
  };
  states?: Array<{
    url: string | null;
    page_signals: Array<{ rule_id: string; severity: string; detail: string }>;
    js_errors: Array<{ rule_id: string; severity: string; message: string; count: number }>;
  }>;
}

export function SlopReport({ payload }: { payload: SlopReportPayload }) {
  const families = payload.families;
  if (!families) return <p>No look data was recorded for this run.</p>;
  const { slop, defects, effort } = families;
  // The per-page JavaScript errors are the evidence behind the defect
  // counts above: a bare count is not something a reader can act on.
  const jsErrorStates = (payload.states ?? []).filter(
    (state) => state.js_errors.length > 0,
  );
  return (
    <section className="slop-report" aria-labelledby="slop-heading">
      <p className="section-label">Check the look — not a verdict</p>
      <h2 id="slop-heading">How the app looks and behaves in code</h2>
      <div className="slop-family-grid">
        <article className="slop-family-card">
          <h3>AI slop</h3>
          <p className="slop-headline">{slop.headline}</p>
          <p className="muted">
            From {slop.judged} judged element(s): {slop.severe} severe, {slop.minor} minor,{" "}
            {slop.clean} clean, {slop.cant_tell} could not be judged. Coverage{" "}
            {Math.round(slop.coverage * 100)}%.
          </p>
          {slop.page_signals.length ? (
            <ul>
              {slop.page_signals.map((signal, index) => (
                <li key={index}>
                  <strong>{signal.rule_id}</strong> ({signal.severity}) — {signal.detail}
                </li>
              ))}
            </ul>
          ) : null}
        </article>
        <article className="slop-family-card">
          <h3>Defects in code</h3>
          <p className="slop-headline">
            {defects.serious} serious · {defects.minor} minor
          </p>
          {defects.per_rule.length ? (
            <ul>
              {defects.per_rule.map((rule) => (
                <li key={rule.rule_id}>
                  <strong>{rule.name}</strong> — {rule.occurrences} occurrence(s) on{" "}
                  {rule.pages.length} page(s)
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No JavaScript errors or code defects were captured.</p>
          )}
        </article>
        <article className="slop-family-card">
          <h3>Effort</h3>
          {effort.value === null ? (
            <p className="muted">{effort.reason}</p>
          ) : (
            <p className="slop-headline">{effort.value}× the reference path</p>
          )}
        </article>
      </div>
      {jsErrorStates.length ? (
        <div className="slop-js-errors">
          <h3>JavaScript errors by page</h3>
          <ul>
            {jsErrorStates.map((state, index) => (
              <li key={index}>
                <strong>{state.url ?? "Unknown page"}</strong>
                <ul>
                  {state.js_errors.map((error, errorIndex) => (
                    <li key={errorIndex}>
                      {error.rule_id} ({error.severity}) — <code>{error.message}</code>
                      {error.count > 1 ? ` ×${error.count}` : ""}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="muted">
        Visited {families.states_visited} page(s). Consistency is measured. Taste is opinion.
      </p>
    </section>
  );
}

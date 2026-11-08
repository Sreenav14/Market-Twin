/**
 * Persona impressions (U-P5-05): quotes grouped by persona, each
 * anchored to the page and the measured signal behind it. There is
 * no verdict and no score on this page by design — impressions are
 * feelings, reported in the persona's own words, and a separate
 * "Impressions" band keeps them apart from the checked results.
 * Quotes render in the theme's human voice (Newsreader italic —
 * "a human said this").
 */

export interface PersonaImpression {
  kind: string;
  quote: string | null;
  journey_url: string | null;
  page_title: string | null;
  signal: Record<string, number | string>;
}

export interface PersonaImpressionsPayload {
  run_kind?: string;
  personas?: Array<{
    persona_id: string;
    persona_name: string | null;
    persona_type: string | null;
    friction_count: number;
    impressions: PersonaImpression[];
  }>;
  total_impressions?: number;
  friction_count?: number;
}

const KIND_WORDS: Record<string, string> = {
  slow_load: "Slow load",
  page_errors: "Something broke",
  small_targets: "Hard to tap",
  no_keyboard_focus: "Keyboard blocked",
  fast_and_clean: "Smooth",
  observation: "Observation",
};

export function PersonaImpressions({ payload }: { payload: PersonaImpressionsPayload }) {
  const personas = payload.personas ?? [];
  return (
    <section className="impressions-band" aria-labelledby="impressions-heading">
      <p className="section-label">Impressions — not a verdict</p>
      <h2 id="impressions-heading">What it felt like</h2>
      <p className="muted">
        {payload.total_impressions ?? 0} impression(s) from {personas.length} persona(s),
        {" "}{payload.friction_count ?? 0} of them friction. These quotes describe feelings
        under real conditions; the ship verdict comes only from the checked results of an
        Explore &amp; Test run.
      </p>
      {personas.map((persona) => (
        <article className="impression-persona" key={persona.persona_id}>
          <h3>{persona.persona_name ?? persona.persona_id}</h3>
          <p className="muted">
            {persona.persona_type} · {persona.impressions.length} impression(s) ·{" "}
            {persona.friction_count} friction
          </p>
          <ul className="impression-list">
            {persona.impressions.map((impression, index) => (
              <li className="impression-item" key={`${persona.persona_id}-${index}`}>
                <blockquote className="impression-quote">{impression.quote}</blockquote>
                <p className="impression-anchor muted">
                  {KIND_WORDS[impression.kind] ?? impression.kind} ·{" "}
                  {impression.journey_url ? (
                    <a className="text-link" href={impression.journey_url} target="_blank" rel="noreferrer">
                      {impression.page_title ?? impression.journey_url}
                    </a>
                  ) : (
                    impression.page_title
                  )}
                  {typeof impression.signal.load_ms === "number"
                    ? ` · loaded in ${(impression.signal.load_ms / 1000).toFixed(1)}s`
                    : ""}
                  {typeof impression.signal.error_count === "number"
                    ? ` · ${impression.signal.error_count} error(s)`
                    : ""}
                  {typeof impression.signal.small_targets === "number"
                    ? ` · ${impression.signal.small_targets} small target(s)`
                    : ""}
                </p>
              </li>
            ))}
          </ul>
        </article>
      ))}
      {personas.length === 0 ? (
        <p>No impressions were recorded for this run.</p>
      ) : null}
    </section>
  );
}

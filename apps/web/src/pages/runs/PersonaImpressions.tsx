import { CountBars } from "../../components/markettwin/ResultFigures";
import { vocabularyWord } from "./reportVocabulary";
import { count, Disclosure, number, record, records, ReportStatus, text } from "./ReportFrame";

export interface PersonaImpressionsPayload {
  run_kind?: string;
  personas?: unknown[];
  total_impressions?: number;
  friction_count?: number;
  collection?: unknown;
}

export const IMPRESSION_WORDS: Record<string, string> = {
  slow_load: "Slow load",
  page_errors: "Something broke",
  small_targets: "Hard to tap",
  no_keyboard_focus: "Keyboard blocked",
  focus_indicator_invisible: "Focus not visible",
  fast_and_clean: "Smooth",
  observation: "Observation",
};

export const PERSONA_TASK_WORDS: Record<string, string> = {
  attempted: "Attempted", timed_out: "Timed out", blocked: "Blocked",
  call_limit_exhausted: "Ended early — step limit reached",
  stopped_at_checkpoint: "Stopped at a review point", unverified: "Not verified",
};

const stopWords: Record<string, string> = {
  lead_stop: "the Lead stopped this task",
  call_limit_exhausted: "the step limit was reached",
  owner_stopped: "you stopped the run",
  timed_out: "the task ran out of time",
  blocked: "the task was blocked",
};
const personaWords: Record<string, string> = {
  keyboard_only: "Keyboard only", first_time: "First-time visitor", first_time_visitor: "First-time visitor",
  first_time_user: "First-time visitor", experienced_user: "Experienced user", mobile_user: "Mobile user",
  mobile: "Mobile user", slow_network: "Slow network", low_vision: "Low vision",
  low_bandwidth: "Slow network", cautious_buyer: "Cautious buyer", power_user: "Power user",
  impatient: "In a hurry", impatient_mobile: "In a hurry on mobile", returning_user: "Returning visitor",
};
const friction = ["slow_load", "page_errors", "small_targets", "no_keyboard_focus", "focus_indicator_invisible"];

function lookup(map: Record<string, string>, value: unknown) {
  const key = text(value) ?? "";
  return Object.hasOwn(map, key) ? map[key] : undefined;
}

export function PersonaTakeaway({ payload }: { payload: PersonaImpressionsPayload }) {
  const personas = records(payload.personas);
  const impressions = personas.flatMap(persona => records(persona.impressions));
  const frictionCount = impressions.filter(item => friction.includes(text(item.kind) ?? "")).length;
  const impressionsRecorded = personas.some(persona => Array.isArray(persona.impressions));
  const collection = record(payload.collection);
  const stopped = records(collection.stopped_personas);
  return <>
    <h2>What it felt like</h2>
    {impressionsRecorded ? <p>{number(impressions.length)} recorded {impressions.length === 1 ? "impression" : "impressions"} from {number(personas.length)} {personas.length === 1 ? "persona" : "personas"} · {number(frictionCount)} about friction</p>
      : <p>No persona impressions were recorded for this run.</p>}
    {collection.partial === true ? <p role="status">Partial run — some personas stopped early</p> : null}
    {collection.owner_stopped === true ? <p>Stopped by you</p> : null}
    {stopped.length ? <Disclosure label="Personas who stopped early">
      <ul>{stopped.map((item, index) => {
        const persona = personas.find(entry => entry.persona_id === item.persona_id);
        return <li key={index}>{text(persona?.persona_name) ?? text(item.persona_id) ?? "Persona"} · {lookup(stopWords, item.stop_kind) ?? "Stop reason not recorded"}</li>;
      })}</ul>
    </Disclosure> : null}
  </>;
}

function KeyboardRecord({ walk }: { walk: Record<string, unknown> }) {
  const steps = records(walk.steps);
  const visible = steps.filter(step => step.indicator_visible === true).length;
  const hidden = steps.filter(step => step.indicator_visible === false).map(step => text(step.name) ?? text(step.role)).filter(Boolean);
  if (count(walk.tabs) === undefined && !text(walk.failure)) return null;
  return <Disclosure label="Keyboard record">
    {count(walk.tabs) !== undefined ? <p>Tab order: {count(walk.tabs)} stops · focus visible on {number(visible)}{hidden.length ? <> · focus not visible on: {hidden.join(", ")}</> : null}</p> : null}
    {text(walk.failure) ? <p>{text(walk.failure)}</p> : null}
  </Disclosure>;
}

export function PersonaImpressions({ payload }: { payload: PersonaImpressionsPayload }) {
  const personas = records(payload.personas);
  if (!personas.length) return null;
  const ranking = friction.map(kind => ({
    label: IMPRESSION_WORDS[kind],
    count: personas.filter(persona => records(persona.impressions).some(item => item.kind === kind && text(item.journey_url))).length,
    color: "teal" as const,
  })).filter(row => row.count > 0).sort((a, b) => b.count - a.count);
  return <section className="report-section">
    <h2>Persona impressions</h2>
    <div className="report-cards">{personas.map((persona, index) => {
      const impressions = records(persona.impressions);
      const frictionCount = impressions.filter(item => friction.includes(text(item.kind) ?? "")).length;
      const walk = record(persona.keyboard_walk);
      return <article className="tester-panel" key={text(persona.persona_id) ?? index}>
        <h3>{text(persona.persona_name) ?? text(persona.persona_id) ?? "Persona"}</h3>
        {lookup(personaWords, persona.persona_type) ? <p>{lookup(personaWords, persona.persona_type)}</p> : null}
        {impressions.length > 0 ? <p>{number(frictionCount)} friction {frictionCount === 1 ? "note" : "notes"}</p> : <p>No impressions were recorded.</p>}
        <ul className="impression-list">{impressions.map((item, i) => {
          const signal = record(item.signal);
          const word = vocabularyWord(IMPRESSION_WORDS, item.kind, "Observation");
          const url = text(item.journey_url);
          const page = text(item.page_title);
          let address: URL | undefined;
          if (url) {
            try { const parsed = new URL(url); if (["http:", "https:"].includes(parsed.protocol)) address = parsed; } catch { address = undefined; }
          }
          return <li key={i} className="impression-item">
            {text(item.quote) ? <blockquote className="impression-quote">{text(item.quote)}</blockquote> : null}
            <ReportStatus word={word} tone="info" />
            {address ? <p><a href={address.href} target="_blank" rel="noreferrer">{[page, address.host + address.pathname].filter(Boolean).join(" · ")}</a></p> : page ? <p>{page}</p> : null}
            {typeof signal.load_ms === "number" ? <span>Loaded in {(signal.load_ms / 1000).toFixed(1)}s </span> : null}
            {count(signal.error_count) !== undefined ? <span>{count(signal.error_count)} errors </span> : null}
            {count(signal.small_targets) !== undefined ? <span>{count(signal.small_targets)} small targets</span> : null}
            {count(signal.tabs) !== undefined && text(signal.element) ? <p>Tabbed through {count(signal.tabs)} stops — focus not visible on {text(signal.element)}</p> : null}
          </li>;
        })}</ul>
        {persona.persona_type === "keyboard_only" && count(walk.tabs) === undefined && !text(walk.failure)
          ? <p><ReportStatus word="Not verified" tone="notchecked" /> · No tab-order record was saved.</p>
          : <KeyboardRecord walk={walk} />}
      </article>;
    })}</div>
    {ranking.length ? <CountBars title="Friction mentioned by personas" rows={ranking.map(row => ({
      ...row, label: `${row.label} · Mentioned by ${number(row.count)} of ${number(personas.length)} personas`,
    }))} /> : null}
  </section>;
}

export function PersonaTasks({ payload }: { payload: PersonaImpressionsPayload }) {
  const personas = records(payload.personas).filter(persona => records(persona.tasks).length);
  if (!personas.length) return null;
  return <section className="report-section"><h2>Persona tasks</h2>
    {personas.map((persona, index) => <section key={text(persona.persona_id) ?? index}>
      <h3>{text(persona.persona_name) ?? text(persona.persona_id) ?? "Persona"}</h3>
      {records(persona.tasks).length ? <Disclosure label="Recorded tasks"><ul className="report-rows">{records(persona.tasks).map((task, i) => {
        const status = vocabularyWord(PERSONA_TASK_WORDS, task.status, "Not verified");
        const ending = lookup(stopWords, task.stop_kind) ?? lookup(stopWords, task.reason);
        return <li key={i}><Disclosure label={<>{text(task.objective) ?? "Task"} · <ReportStatus word={status} tone={task.status === "attempted" ? "info" : "notchecked"} /></>}>
          {text(task.account) ? <p>{text(task.account)}</p> : null}
          {task.source ? <p>Simulated persona attempt</p> : null}
          {task.verified_completion === false ? <p>Not a verified completion</p> : null}
          {ending ? <p>Ended early — {ending}</p> : null}
          {text(task.blocker) ? <p>{text(task.blocker)}</p> : null}
        </Disclosure></li>;
      })}</ul></Disclosure> : null}
    </section>)}
  </section>;
}

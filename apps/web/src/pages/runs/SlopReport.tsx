import { CountBars, CountTrack, StackedBar } from "../../components/markettwin/ResultFigures";
/**
 * Slop report (U-P6-05): three family numbers, never blended.
 * Slop gets its derived percentage (or the honest suppression
 * headline) with its counts always beside it; defects are counts
 * with severities; effort explains itself when no task was
 * performed. There is no verdict here — readiness comes only from
 * an Explore & Test run.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ReportFrame, type DiffItem } from "./ReportFrame";
import { vocabularyWord } from "./reportVocabulary";
import { ArtifactEvidence } from "../../components/markettwin/ArtifactEvidence";
import { AlertTriangle, CircleHelp } from "lucide-react";

type Signal = { rule_id: string; severity: string; detail: string; evidence_artifact_ids?: string[] };

export const ruleNames: Record<string, string> = {
  SLOP_PLACEHOLDER_TEXT: "Placeholder content is still present",
  SLOP_BROKEN_MEDIA: "Image failed to load",
  SLOP_TEMPLATE_CHROME: "Repeated template styling",
  SLOP_GENERIC_PHRASES: "Generic wording needs review",
  SLOP_CONTRAST: "Text contrast is below the measured threshold",
  SLOP_EMOJI_ICONS: "Emoji-heavy control label needs review",
  SLOP_ROUND_STATS: "Generic rounded statistic needs review",
  SLOP_CLIPPED_CONTROL_LABEL: "Primary action text is clipped",
  SLOP_VIEWPORT_INTEGRITY: "Page content overflows the viewport",
  SLOP_DEAD_END: "Page has little content and no controls",
  SLOP_LOW_RES_MEDIA: "Image resolution is below its displayed size",
  SLOP_STRETCHED_IMAGE: "Image proportions are distorted",
  SLOP_DEFAULT_FONT: "Default font",
  SLOP_ACID_DARK: "Dark surfaces use saturated accent colours",
  SLOP_AI_CHROME: "Interface refers to AI or its generator",
  SLOP_ALIGNMENT: "Nearby elements are slightly misaligned",
  SLOP_CARD_GRID: "Cards repeat the same layout",
  SLOP_CENTRED_HERO: "Centred hero layout",
  SLOP_CENTRED_LAYOUT: "Page repeats centred layouts",
  SLOP_COLOUR_DISCIPLINE: "Colour use varies across pages",
  SLOP_COMPONENT_FINGERPRINTS: "Similar components have different styling",
  SLOP_COPY_CADENCE: "Copy repeats the same phrasing pattern",
  SLOP_EDITORIAL_CLUSTER: "Repeated editorial styling",
  SLOP_EMPTY_VISUAL: "Visual area has little content",
  SLOP_FABRICATED_PROOF: "Placeholder proof block",
  SLOP_FLAT_TYPE: "Headings and body text use similar styling",
  SLOP_GENERIC_CTA: "Generic action labels",
  SLOP_GLASS_GLOW: "Glass or glow styling",
  SLOP_GRADIENT_SIGNATURE: "Repeated gradient styling",
  SLOP_MOCK_CHROME: "Browser mockup styling",
  SLOP_MOTION_TELLS: "Repeated animation pattern",
  SLOP_NO_MICROSTATES: "Interactive states have little visual feedback",
  SLOP_SIDE_TAB_BORDER: "Coloured side-tab border",
  SLOP_SPACING_RHYTHM: "Spacing pattern needs review",
  SLOP_STYLE_INCONSISTENCY: "Styling varies within the page",
  SLOP_TEMPLATE_ASSETS: "Template assets",
  SLOP_TYPE_DISCIPLINE: "Typography varies across components",
  SLOP_UNIFORM_RHYTHM: "Sections repeat the same spacing",
  SLOP_UNIFORM_SURFACE: "Surfaces repeat the same styling",
  DEF_JS_UNCAUGHT: "Uncaught JavaScript exception",
  DEF_JS_UNHANDLED_REJECTION: "Unhandled promise rejection",
  DEF_JS_CONSOLE_ERROR: "Browser console error",
};

const measuredElementRules = new Set([
  "SLOP_CLIPPED_CONTROL_LABEL", "SLOP_BROKEN_MEDIA", "SLOP_CONTRAST",
  "SLOP_PLACEHOLDER_TEXT", "SLOP_LOW_RES_MEDIA", "SLOP_STRETCHED_IMAGE",
]);
const measuredPageRules = new Set(["SLOP_VIEWPORT_INTEGRITY"]);
const designNotes = new Set(["SLOP_DEFAULT_FONT", "SLOP_TEMPLATE_CHROME"]);
const observationNames: Record<string, string> = {
  DRAWN_ILLUSTRATION: "Illustration could not be assessed",
  UI_COMPONENT_VARIANT_REVIEW: "Component variants",
  UI_VISUAL_REVIEW: "Visual check needs review",
  UI_STATE_UNASSESSED: "Page states not verified",
};

const laneCauses: Record<string, string> = {
  browser_action: "Browser action failed",
  browser_policy: "Browser policy blocked the action",
  browser_timeout: "Browser action timed out",
  browser_session: "Browser session ended",
  lane_watchdog: "Browser lane stopped responding",
  lane_error: "Browser lane encountered a runtime error",
  session_factory: "Browser session could not start",
};

const severityWords: Record<string, string> = {
  severe: "Severe", serious: "Serious", minor: "Minor", info: "Note", review: "Needs review",
};

const provenanceWords: Record<string, string> = {
  slop_without_severe_tell: "Marked slop with no severe tell recorded",
  slop_minor_with_severe_tell: "Marked minor but a severe tell was recorded",
  slop_minor_gate_unmet: "Marked minor but the minor gate was not met",
};

const number = (value: number) => value.toLocaleString();
const quantity = (value: number, unit: string) => `${number(value)} ${unit}${value === 1 ? "" : "s"}`;
const batchSize = 20;

function Disclosure({ label, children, className }: {
  label: ReactNode; children: ReactNode; className?: string;
}) {
  const [open, setOpen] = useState(false);
  return <details className={className} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>{label}</summary>
    {open ? children : null}
  </details>;
}

export interface SlopReportPayload {
  run_kind?: string;
  coverage?: { partial?: boolean; pages_recorded?: number; desktop_scan?: boolean; pages_pending?: number; paths_activated?: number; paths_not_assessed?: number;
    pending_urls?: string[];
    excluded_documents?: Record<string, string>; sitemap_failures?: number; sitemaps_pending?: number;
    pages_unverified?: number; states_recorded?: number; stop_reason?: string | null; all_lanes_retired?: boolean;
    budget_exhausted?: boolean; owner_stopped?: boolean;
    visual_reviews_unfinished?: number;
    lane_count?: number;
    desktop_budget?: { active_elapsed_seconds?: number; worker_elapsed_seconds?: number;
      human_wait_seconds?: number; stop_reason?: string | null };
    retired_lanes?: Array<{ lane_id: number; cause: string }>;
    interaction_coverage?: Array<{ url: string; viewport: string; path: string; result: string }> } | null;
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
      undecided_weight?: number;
      undecided_basis?: "area" | "count_fallback";
      provenance_errors?: Array<{ url?: string; element_id?: string; problem: string }>;
      prominence_secondary?: number | null;
      page_signals: Signal[];
    };
    defects: {
      serious: number;
      minor: number;
      test_condition_occurrences?: number;
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
    viewport?: string;
    interaction_path?: string;
    screenshot_artifact_id?: string | null;
    measurement_evidence?: Record<string, unknown> | null;
    elements?: Array<{
      element_id: string;
      label: string;
      verdict: string;
      evidence?: Record<string, unknown>;
      component?: { role?: string; region?: string };
      rules_fired: Array<{ rule_id: string; severity: string; values?: Record<string, unknown> }>;
    }>;
    page_signals: Signal[];
    js_errors: Array<{ rule_id: string; severity: string; message: string; count: number;
      kind?: string; url?: string; stack?: string | null }>;
  }>;
}

type ReportState = NonNullable<SlopReportPayload["states"]>[number];
type PriorityLocation = { stateIndex: number; elementId?: string; measurement?: boolean };
type Priority = {
  key: string; rank: number; severity: string; title: string; detail?: string; check?: string;
  locations: PriorityLocation[]; comparison?: string;
  media?: "confirmed" | "unverified";
  componentLabel?: string;
};

function hasMeasurements(values: Record<string, unknown> | null | undefined) {
  return Object.values(values ?? {}).some(value => value != null);
}

function confirmedMediaFailure(values: Record<string, unknown> | undefined) {
  const status = values?.response_status;
  return typeof status === "number" && status >= 400 && status <= 599;
}

function reportPriorities(states: ReportState[], canOpenArtifact: boolean) {
  const priorities = new Map<string, Priority>();
  function add(candidate: Priority) {
    const previous = priorities.get(candidate.key);
    if (!previous) {
      priorities.set(candidate.key, candidate);
      return;
    }
    previous.rank = Math.max(previous.rank, candidate.rank);
    for (const location of candidate.locations) {
      if (!previous.locations.some(item =>
        item.stateIndex === location.stateIndex && item.elementId === location.elementId)) {
        previous.locations.push(location);
      }
    }
  }
  const artifactStates = new Map(states.flatMap((state, stateIndex) =>
    state.screenshot_artifact_id ? [[state.screenshot_artifact_id, stateIndex] as const] : []));
  states.forEach((state, stateIndex) => {
    for (const element of state.elements ?? []) {
      if (!["slop", "slop_minor"].includes(element.verdict) || !hasMeasurements(element.evidence)) continue;
      for (const rule of element.rules_fired.filter(entry => measuredElementRules.has(entry.rule_id))) {
        const label = element.label.trim();
        const clipped = rule.rule_id === "SLOP_CLIPPED_CONTROL_LABEL";
        const placeholder = rule.rule_id === "SLOP_PLACEHOLDER_TEXT";
        const unconfirmedMedia = rule.rule_id === "SLOP_BROKEN_MEDIA" && !confirmedMediaFailure(element.evidence);
        const review = placeholder || unconfirmedMedia;
        add({
          key: rule.rule_id === "SLOP_BROKEN_MEDIA"
            ? JSON.stringify(["media", review, state.url && pendingRoute(state.url), element.component?.role, element.component?.region])
            : `element:${rule.rule_id}:${label.toLowerCase() || `${stateIndex}:${element.element_id}`}:${element.component?.role ?? ""}:${element.component?.region ?? ""}:${state.interaction_path ?? ""}`,
          rank: clipped ? 4 : review ? 0 : rule.severity === "severe" ? 2 : 1,
          severity: review ? "review" : rule.severity,
          componentLabel: !review && element.component?.role && element.component.region &&
            label && !/https?:\/\//i.test(label) ? label : undefined,
          media: rule.rule_id === "SLOP_BROKEN_MEDIA" ? unconfirmedMedia ? "unverified" : "confirmed" : undefined,
          title: unconfirmedMedia ? "Images did not load during the audit"
            : placeholder ? "Possible placeholder text" : vocabularyWord(ruleNames, rule.rule_id, "UI finding"),
          detail: unconfirmedMedia ? "The recorded browser evidence does not establish the cause."
            : rule.rule_id === "SLOP_BROKEN_MEDIA" ? "The server returned an error for the image."
              : placeholder ? "The element contains text that may have been left over from a template."
                : label && !/https?:\/\//i.test(label) ? `“${label}”` : undefined,
          check: clipped ? "Reopen the affected view at the recorded viewport and check that the full action label is visible."
            : placeholder ? "Needs review — this can be intentional in context." : undefined,
          locations: [{ stateIndex, elementId: element.element_id }],
        });
      }
    }
    for (const [signalIndex, signal] of state.page_signals.entries()) {
      if (!["severe", "minor"].includes(signal.severity)) continue;
      const compared = [...new Set((signal.evidence_artifact_ids ?? [])
        .map(id => artifactStates.get(id)).filter((index): index is number => index !== undefined))];
      const differentPages = new Set(compared.map(index => states[index].url).filter(Boolean)).size > 1;
      const pairedProof = signal.severity === "severe" && canOpenArtifact && compared.length === 2 &&
        compared.includes(stateIndex) && differentPages;
      const { client_width, scroll_width } = state.measurement_evidence ?? {};
      const pageMeasurement = measuredPageRules.has(signal.rule_id)
        && typeof client_width === "number" && client_width > 0
        && typeof scroll_width === "number" && scroll_width > client_width + 1;
      if (!pageMeasurement && !pairedProof) continue;
      add({
        key: `page:${signal.rule_id}:${signal.detail}${pairedProof ? `:${[...compared].sort((a, b) => a - b).join(":")}` : ""}`,
        rank: signal.severity === "severe" ? 3 : 1,
        severity: signal.severity,
        title: ruleNames[signal.rule_id] ?? "The same control has conflicting visibility across pages.",
        detail: pairedProof ? "The control was visible on one recorded page and hidden on the other." : "Content extends past the visible width.",
        check: signal.rule_id === "SLOP_VIEWPORT_INTEGRITY"
          ? "Reopen each affected page at its recorded viewport and check that the full content fits without horizontal scrolling."
          : undefined,
        locations: pairedProof ? compared.map(index => ({ stateIndex: index })) : [{ stateIndex, measurement: true }],
        comparison: pairedProof ? `ui-comparison-${stateIndex}-${signalIndex}` : undefined,
      });
    }
  });
  const affected = (priority: Priority) => new Set(priority.locations.map(location => states[location.stateIndex].url).filter(Boolean)).size;
  for (const priority of priorities.values()) {
    const page = states[priority.locations[0].stateIndex].url;
    const pages = affected(priority);
    if (!priority.media && priority.componentLabel && pages > 1) {
      priority.detail = priority.title;
      priority.title = `Fix “${priority.componentLabel}” — clears findings on ${quantity(pages, "page")}`;
    }
    if (!priority.media || !page) continue;
    const count = priority.locations.length;
    const path = pendingRoute(page).replace(/^https?:\/\/[^/]+/, "") || "/";
    priority.title = `${number(count)} ${count === 1 ? "image" : "images"} ${priority.media === "confirmed" ? "failed to load" : "could not be verified"} on ${path}`;
  }
  return [...priorities.values()].sort((a, b) => b.rank - a.rank || affected(b) - affected(a));
}

function proofTarget({ stateIndex, elementId, measurement }: PriorityLocation) {
  if (elementId !== undefined) return `ui-element-${stateIndex}-${elementId}`;
  return measurement ? `ui-measurements-${stateIndex}` : `ui-state-${stateIndex}`;
}

export function lookDiffItems(payload: SlopReportPayload, runId: string): DiffItem[] {
  const states = payload.states ?? [];
  return reportPriorities(states, Boolean(runId)).map(item => ({
    key: item.comparison ? JSON.stringify([item.title, item.detail, item.locations.map(({ stateIndex }) =>
      [states[stateIndex].url, states[stateIndex].viewport, states[stateIndex].interaction_path]).sort()]) : item.key,
    label: item.detail ? `${item.title} · ${item.detail}` : item.title,
    severity: item.severity === "severe" ? "high" : item.severity === "review" ? "info" : "low",
    href: `/runs/${runId}#${item.comparison ?? encodeURIComponent(proofTarget(item.locations[0]))}`,
  }));
}

function pendingRoute(url: string): string {
  try {
    const parsed = new URL(url);
    const fragment = /^#(?:!\/|\/)/.test(parsed.hash) ? parsed.hash.split("?")[0] : "";
    return parsed.origin + parsed.pathname + fragment;
  } catch {
    return url;
  }
}

function pendingPrefix(url: string): string {
  try {
    const { pathname, hash } = new URL(url);
    const parts = (pathname === "/" && /^#!?\//.test(hash) ? hash.replace(/^#!?/, "").split("?")[0] : pathname)
      .split("/").filter(Boolean);
    if (/^(?:en|de|es|fr|it|ja|ko|nl|pt|sv|zh)(?:-[a-z]{2})?$/i.test(parts[0] ?? "")) parts.shift();
    return parts.length ? `/${parts[0]}` : "/";
  } catch {
    return "Unknown path";
  }
}


type BrowserError = ReportState["js_errors"][number];
type Diagnostic = { key: string; error: BrowserError; count: number; pages: Map<string, BrowserError>; environment?: string };

function groupedDiagnostics(states: ReportState[]) {
  const groups = new Map<string, Diagnostic>();
  for (const state of states) {
    for (const error of state.js_errors ?? []) {
      const message = error.message ?? "";
      const environment = error.rule_id === "DEF_JS_CONSOLE_ERROR" && /^Failed to load resource: net::ERR_(EMPTY_RESPONSE|BLOCKED_BY_CLIENT)\b/i.test(message.trim())
        ? /ERR_EMPTY_RESPONSE/i.test(message) ? "The server returned an empty response" : "A resource was blocked by the browser"
        : undefined;
      const key = environment ?? JSON.stringify([error.kind ?? error.rule_id, message.replace(/\d+/g, "N").trim().toLowerCase().slice(0, 200)]);
      let group = groups.get(key);
      if (!group) {
        group = { key, error, environment, count: 0, pages: new Map() };
        groups.set(key, group);
      }
      group.count += error.count;
      if (error.url || state.url) group.pages.set(error.url || state.url!, error);
    }
  }
  return [...groups.values()].sort((a, b) => b.count - a.count);
}

function DiagnosticPages({ pages }: { pages: Diagnostic["pages"] }) {
  const [limit, setLimit] = useState(batchSize);
  return <>
    <ul>{[...pages].slice(0, limit).map(([url, error]) => <li key={url}>{url}
      {error.stack && <Disclosure label="Technical details"><pre>{error.stack}</pre></Disclosure>}
    </li>)}</ul>
    {pages.size > limit && <button type="button" onClick={() => setLimit(limit + batchSize)}>Show more pages</button>}
  </>;
}

function diagnosticRows(groups: Diagnostic[]) {
  return groups.map(({ key, error, count, pages, environment }) => <Disclosure key={key}
    label={`${environment ?? vocabularyWord(ruleNames, error.rule_id, "Browser error")} · ${quantity(count, "occurrence")} · ${quantity(pages.size, "page")}`}>
    {!environment && error.message?.trim() && error.message.trim() !== "undefined" && <p>{error.message}</p>}
    <DiagnosticPages pages={pages} />
  </Disclosure>);
}

function readFragment(hash = window.location.hash) {
  try { return decodeURIComponent(hash.slice(1)); }
  catch { return ""; }
}

type Element = NonNullable<ReportState["elements"]>[number];

function screenshotBounds(values: Record<string, unknown>) {
  const { x, y, width, height } = values;
  if (typeof x === "number" && typeof y === "number" && typeof width === "number" && width > 0 &&
      typeof height === "number" && height > 0) return { x, y, width, height };
}

function ComparisonEvidence({ comparison, states, runId, onClose }: {
  comparison: Priority; states: ReportState[]; runId: string; onClose: () => void;
}) {
  return <>
    <div className="look-panel-actions">
      <h3>Cross-page comparison</h3>
      <button className="secondary-button compact" type="button" onClick={onClose}>Back to audit summary</button>
    </div>
    <p>{comparison.detail ?? comparison.title}</p>
    <div className="look-evidence-columns">
      {comparison.locations.map(({ stateIndex }) => {
        const state = states[stateIndex];
        return <figure className="look-comparison-capture" key={stateIndex}>
          <figcaption className="look-evidence-location">
            {state.url ?? "Recorded page"}{state.viewport && <> · {viewportWord(state.viewport)}</>}
            {state.interaction_path && <> · {state.interaction_path}</>}
          </figcaption>
          {state.screenshot_artifact_id && <ArtifactEvidence runId={runId} artifactId={state.screenshot_artifact_id} autoLoad />}
        </figure>;
      })}
    </div>
  </>;
}

function StateEvidence({ state, stateIndex, element, runId, measurement, onClose }: {
  state: ReportState; stateIndex: number; element?: Element; runId?: string; measurement?: boolean; onClose: () => void;
}) {
  const values = element?.evidence ?? state.measurement_evidence ?? {};
  const bounds = element ? screenshotBounds(values) : undefined;
  const threshold = element?.rules_fired.find(rule => rule.rule_id === "SLOP_CONTRAST")?.values?.threshold;
  const comparisonIds = element || measurement ? [] : [...new Set(state.page_signals.flatMap(signal => signal.evidence_artifact_ids ?? []))]
    .filter(id => id !== state.screenshot_artifact_id);
  const label = typeof values.text === "string" && values.text ? values.text : element?.label;
  const role = typeof values.role === "string" ? values.role : element?.component?.role;
  const { client_width, scroll_width } = values;
  return <>
    <div className="look-panel-actions">
      <h3>{element ? "Element evidence" : measurement ? "Page measurements" : "Page state evidence"}</h3>
      <button className="secondary-button compact" type="button" onClick={onClose}>Back to audit summary</button>
    </div>
    <p className="look-evidence-location">{state.url ?? "Recorded page"}{state.viewport ? ` · ${viewportWord(state.viewport)}` : ""}</p>
    {!element && state.page_signals.filter(signal => signal.rule_id === "UI_STATE_UNASSESSED").map((signal, index) =>
      <p key={index}><strong>Not verified.</strong> {signal.detail}</p>)}
    {state.interaction_path && <p>Reached by {state.interaction_path}</p>}
    <div className="look-evidence-columns">
      <div>
        {runId && state.screenshot_artifact_id && (!element || bounds)
          ? <ArtifactEvidence runId={runId} artifactId={state.screenshot_artifact_id} bounds={bounds} autoLoad={Boolean(element)} />
          : <p>{element ? "No screenshot covers this element — measurements only." : "Screenshot evidence unavailable for this state."}</p>}
        {runId && comparisonIds.map(id => <ArtifactEvidence key={id} runId={runId} artifactId={id} />)}
      </div>
      <div>
        {label && <p>Text: “{label}”</p>}
        {typeof values.name === "string" && values.name !== label && <p>Name: {values.name}</p>}
        {role && <p>Kind: {role.charAt(0).toUpperCase() + role.slice(1)}</p>}
        {bounds && <p>Size: {bounds.width} × {bounds.height} px</p>}
        {bounds && <p>Position: {bounds.x} px from the left · {bounds.y} px from the top</p>}
        {typeof values.color === "string" && <p>Text colour: {values.color}</p>}
        {typeof values.background === "string" && <p>Background: {values.background}</p>}
        {typeof values.font_size === "number" && <p>Text size: {values.font_size} px</p>}
        {typeof values.font_weight === "string" && <p>Text weight: {values.font_weight}</p>}
        {typeof values.contrast_ratio === "number" && <p>Contrast {values.contrast_ratio}:1{typeof threshold === "number" && ` — the threshold is ${threshold}:1`}</p>}
        {typeof client_width === "number" && typeof scroll_width === "number" && scroll_width > client_width &&
          <p>Page scrolls sideways by {scroll_width - client_width} px</p>}
        {typeof values.label_clipped_horizontal_px === "number" && <p>Action text clipped by {values.label_clipped_horizontal_px} px</p>}
        {element?.rules_fired.map(rule => <p key={rule.rule_id}>
          {rule.rule_id === "SLOP_BROKEN_MEDIA" && !confirmedMediaFailure(element.evidence)
            ? "Needs review · Image could not be verified during the audit"
            : `${severityWords[rule.severity] ?? "Finding"} · ${vocabularyWord(ruleNames, rule.rule_id, "UI finding")}`}
          {rule.rule_id === "SLOP_PLACEHOLDER_TEXT" && <> · Needs review — this can be intentional in context.</>}
        </p>)}
        {!hasMeasurements(values) && element && <p>Detailed measurements were not included in this historical report.</p>}
        {!element && !measurement && <StateFindings state={state} stateIndex={stateIndex} />}
        {hasMeasurements(values) || element ? <Disclosure label="Technical details"><pre>{JSON.stringify({
          ...(element && { element_id: element.element_id, rules_fired: element.rules_fired }), measurements: values,
        }, null, 2)}</pre></Disclosure> : null}
      </div>
    </div>
  </>;
}

function viewportWord(value: string) {
  return value === "desktop1280" ? "Desktop" : value === "mobile320" ? "Mobile" : "Other viewport";
}

function StateFindings({ state, stateIndex }: { state: ReportState; stateIndex: number }) {
  const [limit, setLimit] = useState(batchSize);
  const elements = state.elements?.filter(element => element.verdict !== "clean");
  if (!elements) return <p>Element evidence was not included in this historical report.</p>;
  return <>
    <ul>{elements.slice(0, limit).map((element, index) => <li key={element.element_id || index}>
      {element.element_id && Number.isInteger(stateIndex)
        ? <a href={`#${encodeURIComponent(proofTarget({ stateIndex, elementId: element.element_id }))}`}>{element.label || "Recorded element"}</a>
        : element.label || "Recorded element"}
      {" · "}{element.verdict === "cant_tell" ? "Could not judge" : element.verdict === "slop_minor" ? "Slop — minor" : "Slop — severe"}
    </li>)}</ul>
    {elements.length > limit && <button type="button" onClick={() => setLimit(limit + batchSize)}>Show more elements</button>}
  </>;
}

export function SlopReport({ payload, runId, hash, eyebrow, activity, rerunDiff, facts, technical }: {
  payload: SlopReportPayload; runId?: string; hash?: string; eyebrow?: ReactNode; activity?: ReactNode;
  rerunDiff?: ReactNode; facts?: ReactNode; technical?: ReactNode;
}) {
  const [pendingQuery, setPendingQuery] = useState("");
  const [pendingLimit, setPendingLimit] = useState(batchSize);
  const [pendingGroup, setPendingGroup] = useState<string | null>(null);
  const [pendingOpen, setPendingOpen] = useState(false);
  const [stateLimit, setStateLimit] = useState(batchSize);
  const [showFindings, setShowFindings] = useState(false);
  const [diagnosticLimit, setDiagnosticLimit] = useState(batchSize);
  const [pageFilter, setPageFilter] = useState<string | null>(null);
  const [fragment, setFragment] = useState(() => readFragment(hash));
  const evidenceLink = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    if (hash !== undefined) setFragment(readFragment(hash));
  }, [hash]);

  useEffect(() => {
    const update = () => setFragment(readFragment());
    window.addEventListener("hashchange", update);
    window.addEventListener("popstate", update);
    return () => {
      window.removeEventListener("hashchange", update);
      window.removeEventListener("popstate", update);
    };
  }, []);
  useEffect(() => {
    if (!fragment) return;
    const evidence = document.getElementById(fragment);
    evidence?.focus({ preventScroll: true });
    evidence?.scrollIntoView?.({ block: "start" });
  }, [fragment, payload]);

  const families = payload.families;
  if (!families) return <p>No look data was recorded for this run.</p>;
  const { slop, defects, effort } = families;
  const states = payload.states ?? [];
  const coverage = payload.coverage;
  const signals = slop.page_signals ?? [];
  const pending = coverage?.pending_urls ?? signals.filter(signal => signal.rule_id === "AUDIT_PENDING_PAGE")
    .map(signal => signal.detail.replace(/^Not inspected: /, ""));
  const pendingPaths = new Map<string, string[]>();
  for (const url of pending) {
    const route = pendingPrefix(url);
    const urls = pendingPaths.get(route);
    if (urls) urls.push(url);
    else pendingPaths.set(route, [url]);
  }
  const sortedPaths = [...pendingPaths].sort(([a, urls], [b, others]) => others.length - urls.length || a.localeCompare(b));
  const topPaths = sortedPaths.slice(0, 5);
  const otherPending = sortedPaths.slice(5).flatMap(([, urls]) => urls);
  const matching = (pendingGroup === "Other paths" ? otherPending : pendingGroup ? pendingPaths.get(pendingGroup) ?? [] : pending)
    .filter(url => url.toLowerCase().includes(pendingQuery.toLowerCase()));
  const priorities = reportPriorities(states, Boolean(runId));
  const diagnostics = groupedDiagnostics(states);
  const conditions = diagnostics.filter(group => group.environment);
  const conditionCount = conditions.reduce((sum, group) => sum + group.count, 0);
  const legacyConditionCount = defects.test_condition_occurrences === undefined
    ? Math.min(defects.minor, conditionCount, defects.per_rule.find(rule => rule.rule_id === "DEF_JS_CONSOLE_ERROR")?.occurrences ?? 0)
    : 0;
  const browserDiagnostics = diagnostics.filter(group => !group.environment);
  const defectRows = defects.per_rule.map(rule => rule.rule_id === "DEF_JS_CONSOLE_ERROR" && legacyConditionCount > 0
    ? { ...rule, occurrences: Math.max(0, rule.occurrences - legacyConditionCount), pages: [...new Set(browserDiagnostics
      .filter(group => group.error.rule_id === rule.rule_id).flatMap(group => [...group.pages.keys()]))] } : rule)
    .filter(rule => rule.occurrences > 0)
    .sort((a, b) => Number(b.severity === "serious") - Number(a.severity === "serious") || b.occurrences - a.occurrences);
  const maxDefectCount = Math.max(0, ...defectRows.map(rule => rule.occurrences));
  const unverifiedSevereMedia = states.reduce((total, state) => total + (state.elements ?? []).filter(element =>
    element.verdict === "slop" && !confirmedMediaFailure(element.evidence)
      && element.rules_fired.some(rule => rule.rule_id === "SLOP_BROKEN_MEDIA" && rule.severity === "severe")
      && !element.rules_fired.some(rule => rule.rule_id !== "SLOP_BROKEN_MEDIA" && rule.severity === "severe")).length, 0);
  const comparisons = priorities.filter(priority => priority.comparison);
  const isReviewSignal = (signal: Signal) => signal.severity === "review" || designNotes.has(signal.rule_id)
    || signal.rule_id === "SLOP_DEAD_END";
  const recordedObservations = states.flatMap((state, stateIndex) =>
    state.page_signals.filter(isReviewSignal).map(signal => ({ signal, stateIndex })));
  const observationKey = (signal: Signal) => JSON.stringify([signal.rule_id, signal.detail]);
  const recordedKeys = new Set(recordedObservations.map(({ signal }) => observationKey(signal)));
  const observations = new Map<string, { signal: Signal; stateIndex?: number }[]>();
  for (const entry of [...recordedObservations, ...signals.filter(signal =>
    isReviewSignal(signal) && !recordedKeys.has(observationKey(signal)))
    .map(signal => ({ signal }))]) {
    const { signal } = entry;
    const group = observations.get(signal.rule_id) ?? [];
    group.push(entry);
    observations.set(signal.rule_id, group);
  }
  const recorded = coverage?.pages_recorded;
  const unverified = coverage?.pages_unverified;
  const pendingCount = coverage?.pages_pending;
  const partial = coverage?.partial || (pendingCount ?? 0) > 0;
  const budget = coverage?.desktop_budget;
  const wait = Math.round(budget?.human_wait_seconds ?? 0);
  const retiredCount = coverage?.retired_lanes?.length ?? 0;
  const stopReason = coverage?.owner_stopped ? "Stopped by you."
    : coverage?.budget_exhausted || [coverage?.stop_reason, budget?.stop_reason].some(reason => reason === "budget_exhausted" || reason === "time_budget")
      ? "The audit ran out of time."
      : coverage?.all_lanes_retired ? "The scan ended before all pages were checked." : undefined;
  const stateCount = payload.states?.length ?? families.states_visited;
  const judged = slop.judged;
  const gated = slop.percentage != null;
  const score = slop.headline && (gated || !slop.headline.includes("%")) ? slop.headline
    : gated ? `${slop.percentage!.toLocaleString(undefined, { maximumFractionDigits: 1 })}%` : "Insufficient coverage";
  const percent = (value: number) => value.toLocaleString(undefined, {
    style: "percent", maximumFractionDigits: judged > 1000 ? 1 : 0,
  });
  const provenance = slop.provenance_errors ?? [];
  const targetHost = states.find(state => state.url)?.url;
  const stateAnchor = /^ui-(state|measurements|element)-(\d+)(?:-(.+))?$/.exec(fragment);
  const selectedIndex = Number(stateAnchor?.[2]);
  const selectedState = states[selectedIndex];
  const selectedElement = stateAnchor?.[1] === "element"
    ? selectedState?.elements?.find(element => element.element_id === stateAnchor[3]) : undefined;
  const selected = selectedState && (stateAnchor?.[1] !== "element" || selectedElement) ? selectedState : undefined;
  const selectedComparison = comparisons.find(comparison => comparison.comparison === fragment);
  const viewportCounts = states.map((state, index) => {
    const counts = { slop: 0, slop_minor: 0, clean: 0, cant_tell: 0 };
    for (const element of state.elements ?? []) {
      if (Object.hasOwn(counts, element.verdict)) counts[element.verdict as keyof typeof counts]++;
    }
    return { state, index, counts, unverified: state.page_signals.some(signal => signal.rule_id === "UI_STATE_UNASSESSED") };
  }).sort((a, b) => b.counts.slop + b.counts.slop_minor - a.counts.slop - a.counts.slop_minor);
  const filteredStates = viewportCounts.filter(row => !pageFilter || row.unverified === (pageFilter === "unverified"));

  function proofLink(location: PriorityLocation | string, label: string, className = "text-link") {
    const target = typeof location === "string" ? location : proofTarget(location);
    return <a className={className} href={`#${encodeURIComponent(target)}`}
      onClick={event => {
        if (!event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey) {
          evidenceLink.current = event.currentTarget;
          setFragment(target);
        }
      }}>{label}</a>;
  }

  function choosePath(path: string | null) {
    setPendingGroup(path);
    setPendingLimit(batchSize);
    setPendingOpen(true);
  }

  function closeEvidence() {
    window.location.hash = "";
    setFragment("");
    const origin = evidenceLink.current;
    const canRestoreFocus = origin?.isConnected && origin.hash === `#${encodeURIComponent(fragment)}`;
    (canRestoreFocus ? origin : document.getElementById("slop-heading"))?.focus();
  }

  const title = <header className="look-takeaway">
    {eyebrow ?? <p className="section-label">Check the look{targetHost ? ` · ${pendingRoute(targetHost).split("/").slice(0, 3).at(-1)}` : ""}</p>}
    <h2 id="slop-heading" tabIndex={-1}>{partial
      ? coverage?.desktop_scan ? "Partial desktop audit" : "Partial audit"
      : recorded === 0 ? "No pages inspected"
      : recorded !== undefined ? `Audit complete — ${number(recorded)} pages inspected.`
      : "UI quality audit"}</h2>
    {!gated && <p>Score withheld. {slop.undecided_basis === "area" && slop.undecided_weight !== undefined && slop.undecided_weight > 0.1
        ? `The audit could not judge ${percent(slop.undecided_weight)} of the measured element area.`
        : "The audit could not judge enough elements."}</p>}
    {partial && (stopReason || wait > 0) && <p>{stopReason}{wait > 0 && ` The audit waited ${wait >= 60 ? `${number(Math.floor(wait / 60))} min${wait % 60 ? ` ${wait % 60} sec` : ""}` : `${wait} sec`} for a person.`}</p>}
    {partial && retiredCount > 0 && <p>{number(retiredCount)}{coverage?.lane_count ? ` of ${number(coverage.lane_count)}` : ""} browser {retiredCount === 1 ? "lane retired" : "lanes retired"} during the scan.</p>}
    {(recorded !== undefined || pendingCount !== undefined) && <dl className="report-key-figures look-key-figures">
      {recorded !== undefined && <div><dt>Pages inspected</dt><dd>{number(recorded)}</dd></div>}
      {unverified !== undefined && unverified > 0 && <div><dt>Pages unverified</dt><dd>{number(unverified)}</dd></div>}
      {pendingCount !== undefined && (pendingCount > 0
        ? <div><dt>Pending URLs</dt><dd>{number(pendingCount)}</dd></div>
        : <div><dt>Page states recorded</dt><dd>{number(stateCount)}</dd></div>)}
    </dl>}
    {!gated && <a className="text-link" href="#look-coverage">Review measurement limits</a>}
  </header>;

  const first = <section className="look-priorities" aria-labelledby="look-first">
    <h3 id="look-first">What to check first</h3>
    {priorities.length ? <p className="muted">Ranked by severity, type of impact, then how many pages are affected.</p>
      : <p>Nothing needs fixing first in what was checked.</p>}
    <div className="look-priority-grid">{priorities.slice(0, 3).map(({ key, title, detail, check, locations, severity, comparison, media }) => {
      const pages = [...new Set(locations.map(location => states[location.stateIndex].url).filter(Boolean))];
      const firstPath = pages[0] && (pendingRoute(pages[0]).replace(/^https?:\/\/[^/]+/, "") || "/");
      return <article className="look-card" key={key}>
        <span className="look-severity" data-severity={severity}><AlertTriangle size={14} aria-hidden="true" />{severityWords[severity] ?? "Finding"}</span>
        <h4>{title}</h4>
        {detail && <p>{detail}</p>}
        {check && <p>{check}</p>}
        <p className="look-meta">{quantity(pages.length, "page")} affected · {quantity(locations.length, "occurrence")}</p>
        {firstPath && <p className="look-meta"><span className="look-evidence-location">{firstPath}</span>
          {pages.length > 1 && <> + {number(pages.length - 1)} more {pages.length === 2 ? "page" : "pages"}</>}</p>}
        {proofLink(comparison ?? locations[0], comparison ? "See comparison evidence" : "See evidence", "text-link look-card-link")}
        {locations.length > 1 && <Disclosure label={media ? "Image instances" : "Affected pages"}>
          <ul>{locations.slice(0, 10).map(location => <li key={proofTarget(location)}>{proofLink(location, media
            ? states[location.stateIndex].elements?.find(element => element.element_id === location.elementId)?.label || "Image evidence"
            : states[location.stateIndex].url ?? "Recorded page")}</li>)}</ul>
          {locations.length > 10 && <p>and {number(locations.length - 10)} more</p>}
        </Disclosure>}
      </article>;
    })}</div>
    {priorities.length > 3 && <a href="#look-inventory" className="secondary-button compact" onClick={() => {
      setShowFindings(true);
      setStateLimit(batchSize);
    }}>All findings</a>}
  </section>;

  const middle = <div className="slop-family-grid">
    <article className="slop-family-card">
      <h3>UI slop score</h3>
      <p className="slop-headline">{gated ? <span className="look-figure">{score}</span> : <><CircleHelp size={19} aria-hidden="true" />{score}</>}</p>
      <p className="look-meta">{gated ? "of " : ""}{quantity(judged, "judged element")} · {number(slop.severe)} severe flags · {number(slop.minor)} minor flags · {number(slop.clean)} clean · {number(slop.cant_tell)} could not be judged</p>
      {unverifiedSevereMedia > 0 && <p className="look-meta">The severe flag count includes {quantity(unverifiedSevereMedia, "image observation")} that could not be verified.</p>}
      {!gated && <p>This describes the inspected pages only.</p>}
      {provenance.length > 0 && <Disclosure label={`${number(provenance.length)} elements failed the score’s self-check`}>
        <p>Review the recorded measurements before relying on this score.</p>
        <ul>{provenance.slice(0, batchSize).map((issue, index) => <li key={index}>
          {issue.url} {issue.element_id} · {provenanceWords[issue.problem] ?? "Score self-check issue"}
        </li>)}</ul>
      </Disclosure>}
      <CountBars title="Flagged element observations" rows={[
        { label: "Severe", count: slop.severe, color: "coral" }, { label: "Minor", count: slop.minor, color: "amber" },
      ]} />
      <p>{percent(slop.coverage)} of discovered elements could be judged.
        {gated ? " The score requires at least 80%."
          : slop.coverage >= 0.8 && slop.undecided_weight !== undefined && slop.undecided_weight > 0.1
            ? ` ${percent(slop.undecided_weight)} of ${slop.undecided_basis === "area" ? "measured element area"
              : slop.undecided_basis === "count_fallback" ? "inspected elements" : "the measured sample"} was inconclusive. The limit is 10%.`
            : " The score requires at least 80% coverage."}
      </p>
      <Disclosure label="How the score is weighted"><p>A severe flag contributes two points and a minor flag contributes one.
        The maximum is two points per judged element.</p></Disclosure>
      <p>{comparisons.length > 0 ? `${number(comparisons.length)} supported cross-page ${comparisons.length === 1 ? "mismatch" : "mismatches"}`
        : "Cross-page consistency: Not assessed"}</p>
      {comparisons.length > 0 && <Disclosure label="Cross-page comparison evidence">
        <ul>{comparisons.slice(0, batchSize).map(item => <li key={item.key}>{proofLink(item.comparison!, item.title)}</li>)}</ul>
      </Disclosure>}
    </article>
    <article className="slop-family-card">
      <h3>JavaScript signals</h3>
      <p className="slop-headline"><span><span className="look-figure">{number(defects.serious)}</span> serious · <span className="look-figure">{number(Math.max(0, defects.minor - legacyConditionCount))}</span> minor</span></p>
      <p className="look-meta">Occurrences of grouped JavaScript defects</p>
      {(defects.test_condition_occurrences ?? conditionCount) > 0 && <p>
        <a href="#look-test-conditions" className="text-link">{number(defects.test_condition_occurrences ?? conditionCount)} test conditions</a> recorded separately.
      </p>}
      {defectRows.map(rule => <Disclosure key={rule.rule_id}
          label={<>{vocabularyWord(ruleNames, rule.rule_id, "Browser defect")} · {severityWords[rule.severity] ?? "Recorded"} · {quantity(rule.occurrences, "occurrence")} · {quantity(rule.pages.length, "page")}
            <span className="look-defect-track"><CountTrack count={rule.occurrences} maximum={maxDefectCount} color={rule.severity === "serious" ? "coral" : "amber"} /></span></>}>
          <DiagnosticPages pages={new Map(rule.pages.map(url => [url, { rule_id: rule.rule_id, severity: rule.severity, message: "", count: 0 }]))} />
        </Disclosure>)}
    </article>
    <article className="slop-family-card">
      <h3>Effort</h3>
      <p className="slop-headline">{effort.value == null ? "Not measured" : `${effort.value}× the reference path`}</p>
      {effort.reason && <p>{effort.reason}</p>}
    </article>
  </div>;

  const coverageSection = <section aria-labelledby="look-coverage">
    <h3 id="look-coverage" tabIndex={-1}>Coverage</h3>
    {coverage ? <>
      {recorded !== undefined && <StackedBar unit="pages" total={recorded + (unverified ?? 0)} selected={pageFilter}
        onSelect={value => { setPageFilter(value); setShowFindings(false); setStateLimit(batchSize); }}
        segments={[
          { key: "recorded", word: "Inspected", count: recorded, tone: "works" },
          ...(unverified === undefined ? [] : [{ key: "unverified", word: "Unverified", count: unverified, tone: "notchecked" as const }]),
        ]} />}
      <p>{number(stateCount)} page states recorded</p>
      {unverified !== undefined && unverified > 0 && <p>{number(unverified)} pages unverified</p>}
      {(pendingCount ?? 0) > 0 && <p>{number(pendingCount!)} pending URLs
        {pendingCount === pending.length && pendingPaths.size > 0 ? ` across ${number(pendingPaths.size)} site sections` : ""}</p>}
      <Disclosure label="Coverage details">
        {coverage.desktop_scan && <p>Desktop scan (1280 px). Coverage reflects rendered pages and visible controls.</p>}
        {coverage.stop_reason && <p>{coverage.stop_reason}</p>}
        {coverage.desktop_budget?.stop_reason && coverage.desktop_budget.stop_reason !== coverage.stop_reason && <p>{coverage.desktop_budget.stop_reason}</p>}
        {(coverage.visual_reviews_unfinished ?? 0) > 0 && <p>Visual review unfinished — {number(coverage.visual_reviews_unfinished!)} pages</p>}
        {(coverage.sitemap_failures ?? 0) > 0 && <p>{number(coverage.sitemap_failures!)} sitemap entries could not be read</p>}
        {(coverage.paths_not_assessed ?? 0) > 0 && <p>{number(coverage.paths_not_assessed!)} discovered paths were not assessed</p>}
        {(coverage.desktop_budget?.human_wait_seconds ?? 0) > 0 && <p>Waited {number(coverage.desktop_budget!.human_wait_seconds!)} seconds for a person to act</p>}
        {coverage.desktop_budget?.active_elapsed_seconds !== undefined &&
          <p>{number(coverage.desktop_budget.active_elapsed_seconds)} seconds active
            {coverage.desktop_budget.worker_elapsed_seconds !== undefined &&
              ` · ${number(coverage.desktop_budget.worker_elapsed_seconds)} seconds total`}</p>}
        {Object.entries(coverage.excluded_documents ?? {}).length > 0 && <Disclosure label="Excluded documents">
          <ul>{Object.entries(coverage.excluded_documents ?? {}).slice(0, batchSize).map(([url, reason]) =>
            <li key={url}>{url} ({reason === "non_page_url" ? "non-page document" : "excluded"})</li>)}</ul>
        </Disclosure>}
        {coverage.interaction_coverage?.length ? <Disclosure label="Controls and UI states considered">
          <ul>{coverage.interaction_coverage.slice(0, batchSize).map((entry, index) =>
            <li key={index}>{entry.url} · {viewportWord(entry.viewport)} · {entry.path}</li>)}</ul>
        </Disclosure> : null}
      </Disclosure>
    </> : <p>Coverage is not recorded in this report</p>}
    {topPaths.length > 0 && <figure className="look-pending-chart">
      <figcaption>Where pages remain unchecked</figcaption>
      {topPaths.map(([path, urls], index) => <button
        key={path} type="button" className="look-path" aria-label={`${path}, ${number(urls.length)} pending URLs`}
        aria-pressed={pendingGroup === path} onClick={() => choosePath(pendingGroup === path ? null : path)}>
        <span>{path}</span><span className="look-path-track" aria-hidden="true"><i style={{
          width: `${100 * urls.length / topPaths[0][1].length}%`,
          opacity: [1, .72, .48][index] ?? .32,
        }} /></span><strong>{quantity(urls.length, "URL")}</strong>
      </button>)}
      {otherPending.length > 0 && <button type="button" className="secondary-button compact"
        aria-pressed={pendingGroup === "Other paths"} onClick={() => choosePath(pendingGroup === "Other paths" ? null : "Other paths")}>
        Browse {number(otherPending.length)} URLs in other sections
      </button>}
    </figure>}
    {pending.length > 0 && <details id="look-pending" open={pendingOpen} onToggle={event => setPendingOpen(event.currentTarget.open)}>
      <summary>Browse pending URLs ({number(pending.length)})</summary>
      {pendingOpen && <>
        {pendingGroup && <p>Showing {pendingGroup} <button type="button" onClick={() => choosePath(null)}>Clear</button></p>}
        <label>Find a pending URL <input value={pendingQuery} onChange={event => { setPendingQuery(event.target.value); setPendingLimit(batchSize); }} /></label>
        <ul className="look-url-list">{matching.slice(0, pendingLimit).map((url, index) => <li key={`${url}:${index}`}>{url} · Pending</li>)}</ul>
        {!matching.length && <p>No matching URLs.</p>}
        {matching.length > pendingLimit && <button type="button" onClick={() => setPendingLimit(pendingLimit + batchSize)}>Show more URLs</button>}
      </>}
    </details>}
  </section>;

  const observationsSection = (diagnostics.length > 0 || observations.size > 0 || (defects.test_condition_occurrences ?? 0) > 0) && <section aria-labelledby="look-observations">
    <h3 id="look-observations">Observations and diagnostics</h3>
    {observations.size > 0 && <section className="look-observation-band">
      <h4>Design observations — unconfirmed</h4>
      <p>These notes need human review before you act on them.</p>
      {[...observations].map(([key, group]) => <Disclosure key={key}
        label={`${observationNames[key] ?? vocabularyWord(ruleNames, key, "Other recorded observations")} · ${quantity(group.length, "observation")}`}>
        <ul>{group.slice(0, batchSize).map(({ signal, stateIndex }, index) => <li key={index}>
          {signal.detail}
          {signal.rule_id === "SLOP_DEAD_END" && " Check whether the page finished loading."}
          {stateIndex !== undefined && <> · {proofLink({ stateIndex }, states[stateIndex].url ?? "Page evidence")}</>}
        </li>)}</ul>
      </Disclosure>)}
    </section>}
    {browserDiagnostics.length > 0 && <section><h4>Browser diagnostics</h4>{diagnosticRows(browserDiagnostics.slice(0, diagnosticLimit))}
      {browserDiagnostics.length > diagnosticLimit && <button type="button" onClick={() => setDiagnosticLimit(diagnosticLimit + batchSize)}>Show more diagnostics</button>}
    </section>}
    {(defects.test_condition_occurrences ?? conditionCount) > 0 && <section id="look-test-conditions">
      <h4>Test conditions</h4>
      {conditions.length ? diagnosticRows(conditions) : <p>No individual test-condition records are available.</p>}
    </section>}
  </section>;

  const inventory = <section id="look-inventory" tabIndex={-1} aria-labelledby="look-inventory-heading">
    <div className="look-panel-actions">
      <h3 id="look-inventory-heading">{showFindings ? "Grouped findings" : "State inventory"}</h3>
      {priorities.length > 0 && <button type="button" className="secondary-button compact" onClick={() => {
        setShowFindings(!showFindings); setStateLimit(batchSize);
      }}>{showFindings ? "Show page states" : "Show findings"}</button>}
    </div>
    {!showFindings && pageFilter && <p>Showing {pageFilter} pages</p>}
    {showFindings ? <ul className="look-inventory-list">{priorities.slice(0, stateLimit).map(item => <li key={item.key}>
      <strong>{item.title}</strong> · {item.detail} · {quantity(item.locations.length, "occurrence")} · {proofLink(item.comparison ?? item.locations[0], "See evidence")}
    </li>)}</ul> : <ul className="look-inventory-list">{filteredStates.slice(0, stateLimit).map(({ state, index, counts, unverified }) => <li key={index}>
      {proofLink({ stateIndex: index }, state.url ?? "Recorded page")} {state.viewport && <>· {viewportWord(state.viewport)}</>}
      {unverified ? <span className="look-verification-chip"><CircleHelp size={14} aria-hidden="true" />Not verified</span>
        : state.elements && <span className="look-meta">{number(counts.slop)} severe · {number(counts.slop_minor)} minor · {number(counts.clean)} clean · {number(counts.cant_tell)} could not judge</span>}
    </li>)}</ul>}
    {(showFindings ? priorities.length : filteredStates.length) > stateLimit &&
      <button type="button" className="secondary-button compact" onClick={() => setStateLimit(stateLimit + batchSize)}>Show more {showFindings ? "findings" : "states"}</button>}
    {!showFindings && filteredStates.length === 0 && <p>No matching page states recorded.</p>}
  </section>;

  const evidence = (selected || selectedComparison) && <section className="look-evidence-panel look-card" id={fragment}
      tabIndex={-1} aria-label="Recorded evidence">
      {selected && <StateEvidence key={fragment} state={selected} stateIndex={selectedIndex} element={selectedElement} runId={runId}
        measurement={stateAnchor?.[1] === "measurements"} onClose={closeEvidence} />}
      {selectedComparison && runId && <ComparisonEvidence key={fragment} comparison={selectedComparison}
        states={states} runId={runId} onClose={closeEvidence} />}
    </section>;
  return <section className="look-report" aria-labelledby="slop-heading">
    <ReportFrame takeaway={title} rerunDiff={rerunDiff} activity={activity} first={<>{first}{evidence}</>} middle={middle}
      coverage={coverageSection} observations={observationsSection} inventory={inventory} facts={facts}
      technical={<>{slop.prominence_secondary != null && <p>Mean per-page load score: {slop.prominence_secondary}</p>}
        {coverage?.retired_lanes?.length ? <ul>{coverage.retired_lanes.map(({ lane_id, cause }) =>
          <li key={lane_id}>Lane {lane_id + 1}: {laneCauses[cause] ?? "Browser lane ended"}</li>)}</ul> : null}{technical}</>} />
  </section>;
}

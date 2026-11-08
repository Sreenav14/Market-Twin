import { useEffect, useMemo, useRef, useState } from "react";
import { VoiceCard } from "../../components/ui/VoiceCard";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";
import type { AppShellContext } from "../../layouts/AppShell";
import {
  api,
  type Application,
  type HumanAction,
  type JourneyExecution,
  type RunResults,
  type TestRun,
} from "../../lib/api";
import { testReference, testTitle } from "../../lib/format";
import { formatDate, marketVerdictWord } from "../../lib/results";
import { statusEntry } from "../../lib/status";
import { canWriteWorkspace } from "../../lib/permissions";
import { useWorkspaceTests } from "../../lib/useWorkspaceTests";
import { ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { InlineAlert } from "../../components/ui/Feedback";
import { TestStatusBadge } from "../../components/ui/StatusBadge";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { splitMetrics } from "../runs/ContractReport";
import { CANONICAL_DEMO_DATA } from "../../lib/concept-dataset";
import {
  canAnimateDesk,
  DeskMotionContext,
  DeskScaleFill,
  DeskSwap,
  DeskZone,
  useDeskEnterFlip,
  useDocumentHidden,
  useFlip,
  usePrefersReducedMotion,
  type DeskMotionState,
} from "./deskMotion";

function isApprovedReplayDraft(test: TestRun): boolean {
  const contract = test.configuration_snapshot.test_contract;
  return test.status === "draft"
    && typeof test.configuration_snapshot.frozen_contract_source_run_id === "string"
    && typeof contract === "object" && contract !== null
    && "status" in contract && contract.status === "approved";
}

export function testDestination(test: TestRun): { to: string; label: string } {
  const base = `/runs/${test.id}`;
  if (isApprovedReplayDraft(test)) return { to: `${base}/contract`, label: "Run approved tests" };
  if (test.configuration_snapshot.discovery_stage === "awaiting_approval") {
    return { to: `${base}/contract`, label: "Approve the tests" };
  }
  if (test.status === "awaiting_human") return { to: `${base}/human-action`, label: "Help this tester" };
  if (test.status === "completed") return { to: `${base}/results`, label: "See test results" };
  // Only a run that is actually executing has a live browser to watch;
  // a queued or planning run gets its details page, not a live claim.
  if (test.status === "running") return { to: `${base}/watch`, label: "Watch live" };
  return { to: `${base}/overview`, label: test.status === "draft" ? "Review draft" : "See test details" };
}

/** The one-line outcome of a finished run, from its real report payload:
 * "1 of 2 journeys worked · 0 findings". Null when the report carries no
 * journey tally — Home shows nothing rather than inventing a figure. */
export function runOutcomeLine(results: RunResults): string | null {
  const parts: string[] = [];
  const payload = results.report.payload as Record<string, unknown> | null;
  const journeys = payload && typeof payload === "object"
    ? (payload as Record<string, unknown>).journeys as Record<string, unknown> | undefined
    : undefined;
  const counts = journeys?.outcome_counts as Record<string, unknown> | undefined;
  const total = typeof journeys?.total === "number" ? journeys.total : undefined;
  const passed = typeof counts?.passed === "number" ? counts.passed : undefined;
  if (total !== undefined && passed !== undefined) {
    parts.push(`${passed} of ${total} ${total === 1 ? "journey" : "journeys"} worked`);
  }
  parts.push(`${results.findings.length} ${results.findings.length === 1 ? "finding" : "findings"}`);
  return parts.length ? parts.join(" · ") : null;
}

/* ---------- Report payload reading (the same derivations the results
   page makes, so Home and the report can never disagree) ---------- */

function obj(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function rowsOf(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(obj) : [];
}
function numOf(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function strOf(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

type DeskOutcome = "worked" | "broken" | "could_not_check" | "not_checked";

function contractOutcomes(payload: Record<string, unknown>): Record<DeskOutcome, number> | null {
  const verdict = obj(payload.market_verdict);
  if (typeof verdict.verdict !== "string") return null;
  const journeys = rowsOf(payload.journeys);
  const works = new Set((Array.isArray(payload.what_works) ? payload.what_works : []).filter((v): v is string => typeof v === "string"));
  const confirmedKeys = new Set(rowsOf(payload.confirmed).map((item) => strOf(item.journey_key)));
  const cases = rowsOf(payload.cases);
  const hasCases = Array.isArray(payload.cases);
  const executedKeys = new Set(cases.filter((c) => c.verdict !== "not_run").map((c) => strOf(c.journey_key)));
  const counts: Record<DeskOutcome, number> = { worked: 0, broken: 0, could_not_check: 0, not_checked: 0 };
  for (const journey of journeys) {
    const key = strOf(journey.journey_key);
    if (works.has(key)) counts.worked += 1;
    else if (confirmedKeys.has(key)) counts.broken += 1;
    else if (hasCases && !executedKeys.has(key)) counts.not_checked += 1;
    else counts.could_not_check += 1;
  }
  return counts;
}

function journeyTitles(payload: Record<string, unknown>): Record<string, string> {
  const titles: Record<string, string> = {};
  for (const journey of rowsOf(payload.journeys)) titles[strOf(journey.journey_key)] = strOf(journey.title);
  return titles;
}

interface DeskVoice { quote: string; name: string }

/** Verbatim tester quotes from the report payload, metric tokens
 * stripped exactly as the results page strips them. No scores. */
function voicesOf(results: RunResults): DeskVoice[] {
  const payload = obj(results.report.payload);
  const personas = rowsOf(obj(payload.experience).personas);
  const voices: DeskVoice[] = [];
  for (const persona of personas) {
    if (persona.status !== "completed") continue;
    const dimensions = obj(obj(persona.scores).dimensions);
    for (const dimension of ["ease", "clarity", "trust", "visual_quality"]) {
      const justification = strOf(obj(dimensions[dimension]).justification).trim();
      if (justification) {
        voices.push({ quote: splitMetrics(justification).clean, name: strOf(persona.name ?? persona.persona_name, "Tester") });
        break;
      }
    }
    if (voices.length >= 3) break;
  }
  return voices;
}

interface DeskEvidence { title: string; detail: string }

/** The masthead's evidence block: the strongest single piece of
 * evidence behind the verdict, from the payload itself. */
function evidenceOf(results: RunResults, verdictKey: string | null, voices: DeskVoice[]): DeskEvidence | null {
  const payload = obj(results.report.payload);
  const titles = journeyTitles(payload);
  if (verdictKey) {
    const confirmed = rowsOf(payload.confirmed);
    if ((verdictKey === "not_ready" || verdictKey === "ready_with_issues") && confirmed.length) {
      const first = confirmed[0];
      return {
        title: `Failed: ${strOf(first.check, "Approved check failed")}`,
        detail: `${titles[strOf(first.journey_key)] ? `${titles[strOf(first.journey_key)]} · ` : ""}Reproduced in a fresh browser.`,
      };
    }
    if (verdictKey === "insufficient_evidence") {
      const outcomes = contractOutcomes(payload);
      const journeys = rowsOf(payload.journeys);
      const confirmedKeys = new Set(rowsOf(payload.confirmed).map((item) => strOf(item.journey_key)));
      const works = new Set((Array.isArray(payload.what_works) ? payload.what_works : []).filter((v): v is string => typeof v === "string"));
      const stuck = journeys.find((journey) => {
        const key = strOf(journey.journey_key);
        return !works.has(key) && !confirmedKeys.has(key);
      });
      if (stuck) return { title: strOf(stuck.title, "A journey"), detail: "Could not be checked." };
      if (outcomes && outcomes.could_not_check > 0) return { title: `${outcomes.could_not_check} of ${outcomes.worked + outcomes.broken + outcomes.could_not_check + outcomes.not_checked} journeys`, detail: "Could not be checked." };
      return null;
    }
    // ready: the strongest positive evidence, plus a tester's words.
    const outcomes = contractOutcomes(payload);
    if (outcomes) {
      const total = outcomes.worked + outcomes.broken + outcomes.could_not_check + outcomes.not_checked;
      if (total > 0) {
        return {
          title: `${outcomes.worked} of ${total} ${total === 1 ? "journey" : "journeys"} worked`,
          detail: voices.length ? `“${voices[0].quote}” — ${voices[0].name}, simulated tester` : "Every approved check passed.",
        };
      }
    }
    return null;
  }
  // Legacy payloads carry no market verdict; the findings list is the evidence.
  const verified = results.findings.find((finding) => finding.verification_status?.startsWith("verified"));
  if (verified) return { title: verified.title, detail: "Reproduced in a fresh browser." };
  if (results.findings.length) return { title: results.findings[0].title, detail: "Seen once — not yet reproduced." };
  return null;
}

function truncateWords(text: string, limit: number): string {
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit);
  const lastSpace = cut.lastIndexOf(" ");
  return `${cut.slice(0, lastSpace > 40 ? lastSpace : limit).trimEnd()}…`;
}

/* ---------- The Briefing Desk ---------- */

type RecentFilter = "all" | "completed" | "failed" | "cancelled";

const APP_TILE_TINTS = ["#E6F2F5", "#FEF3C7", "#E6F4EA", "#FDECEC", "#F3E8EE", "#E8F1F8"];
function tileTint(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  return APP_TILE_TINTS[hash % APP_TILE_TINTS.length];
}

export function WorkspaceDashboardPage() {
  const { user, workspace } = useOutletContext<AppShellContext>();
  const state = useWorkspaceTests(user.id, workspace.id);
  const writable = canWriteWorkspace(workspace.role);
  const [recentFilter, setRecentFilter] = useState<RecentFilter>("all");
  const runs = [...(state.data?.runs ?? [])].sort((a, b) => (Date.parse(b.created_at ?? "") || 0) - (Date.parse(a.created_at ?? "") || 0));
  const applications = state.data?.applications ?? [];
  const appById = new Map(applications.map((app) => [app.id, app]));
  const appName = (run: TestRun) => appById.get(run.application_id)?.name ?? "Your app";

  const awaitingRuns = runs.filter((test) => test.status === "awaiting_human");
  const approvalRuns = runs.filter((test) => isApprovedReplayDraft(test) || test.configuration_snapshot.discovery_stage === "awaiting_approval");
  const activeRuns = runs.filter((test) => ["planning", "queued", "running"].includes(test.status));
  const finishedRuns = runs.filter((test) => ["completed", "failed", "cancelled"].includes(test.status));
  const completedRuns = runs.filter((test) => test.status === "completed");
  const latestFailed = finishedRuns[0]?.status === "failed" ? finishedRuns[0] : null;
  const latestCompleted = completedRuns[0] ?? null;
  const previousCompleted = latestFailed ? (completedRuns[0] ?? null) : null;

  const humanActionQueries = useQueries({
    queries: awaitingRuns.slice(0, 3).map((run) => ({
      queryKey: ["home-human-actions", user.id, workspace.id, run.id],
      queryFn: ({ signal }: { signal: AbortSignal }) => api.listHumanActions(run.id, signal),
      refetchInterval: 5_000,
    })),
  });
  const stripQueries = useQueries({
    queries: activeRuns.slice(0, 3).map((run) => ({
      queryKey: ["home-strip-journeys", user.id, workspace.id, run.id],
      queryFn: ({ signal }: { signal: AbortSignal }) => api.getRunJourneys(run.id, signal),
      refetchInterval: 5_000,
    })),
  });
  const knowledge = useQuery({
    queryKey: ["home-knowledge-review", user.id, workspace.id],
    queryFn: () => api.listIngestion(workspace.id),
  });
  const featuredResults = useQuery({
    queryKey: ["home-featured-results", user.id, workspace.id, latestCompleted?.id],
    queryFn: ({ signal }) => api.getRunResults(latestCompleted!.id, signal),
    enabled: Boolean(latestCompleted),
    retry: false,
  });

  /* ----- Motion (deskMotion.tsx). The gate stays unarmed until the
     first desk content has painted, so nothing animates on arrival —
     only on a change that happens while the user is looking. The
     loading/error returns live further down, below every hook. ----- */
  const reducedMotion = usePrefersReducedMotion();
  const documentHidden = useDocumentHidden();
  const armedRef = useRef(false);
  const motion = useMemo<DeskMotionState>(
    () => ({ armedRef, reduced: reducedMotion, suspended: documentHidden }),
    [reducedMotion, documentHidden],
  );
  useEffect(() => {
    if (state.data) armedRef.current = true;
  }, [state.data]);
  const deskRef = useRef<HTMLDivElement>(null);
  const trayCardsRef = useRef<HTMLDivElement>(null);
  const archiveRowsRef = useRef<HTMLDivElement>(null);
  const archiveFlipGateRef = useRef(0);

  const newTestPath = applications.length === 1 ? `/applications/${applications[0].id}/runs/new` : "/applications";

  /* ----- Needs-you items, in the tray's order: the Lead Agent's
     requests first (earliest waiting first), then test approvals,
     then knowledge reviews. ----- */
  type TrayItem =
    | { kind: "human"; run: TestRun; action: HumanAction }
    | { kind: "approval"; run: TestRun }
    | { kind: "knowledge"; id: string; name: string; sourceName: string };
  const trayItems: TrayItem[] = [];
  awaitingRuns.slice(0, 3).forEach((run, index) => {
    const actions = (humanActionQueries[index]?.data ?? [])
      .filter((action) => action.status === "pending")
      .sort((a, b) => (Date.parse(a.created_at) || 0) - (Date.parse(b.created_at) || 0));
    for (const action of actions) trayItems.push({ kind: "human", run, action });
  });
  for (const run of approvalRuns) trayItems.push({ kind: "approval", run });
  for (const entry of knowledge.data ?? []) {
    if (entry.status === "draft" && entry.processing_stage === "review") {
      trayItems.push({ kind: "knowledge", id: entry.id, name: entry.name, sourceName: entry.source_name });
    }
  }
  const blocked = trayItems.length > 0;

  const trayItemKey = (item: TrayItem): string =>
    item.kind === "human" ? `human-${item.action.id}`
      : item.kind === "approval" ? `approval-${item.run.id}`
        : `knowledge-${item.id}`;

  /* ----- The one attention event: a Needs-you item arriving while the
     user is present. The first set of items only seeds the seen-set —
     nothing fires on mount. A genuinely new item earns the one-shot
     enter (fade + 4px lift, flame wash decaying over ~600ms) and then
     keeps a static flame edge until it leaves the tray. Several items
     in one poll are one tray-level event. Under reduced motion, or
     while the document is hidden, only the edge appears, instantly.
     Focus is never moved; the tray region is aria-live="polite". ----- */
  const trayIdsKey = trayItems.map(trayItemKey).join("|");
  const seenTrayRef = useRef<ReadonlySet<string> | null>(null);
  const [trayNewIds, setTrayNewIds] = useState<ReadonlySet<string>>(new Set());
  const [trayEnteringIds, setTrayEnteringIds] = useState<ReadonlySet<string>>(new Set());
  // Seeding waits until the desk's own data has painted AND every tray
  // source has settled at least once — before that, items are still
  // arriving as part of the initial load, and load sequencing must
  // never read as an arrival. (With no runs loaded yet there are no
  // awaiting runs, so "no action queries" would otherwise look settled
  // and seed an empty set during the loading panel.)
  const traySourcesSettled =
    Boolean(state.data) &&
    humanActionQueries.every((query) => query.data !== undefined || query.isError) &&
    (knowledge.data !== undefined || knowledge.isError);
  useEffect(() => {
    const current = new Set(trayItems.map(trayItemKey));
    if (seenTrayRef.current === null) {
      if (traySourcesSettled) seenTrayRef.current = current;
      return;
    }
    const arrivals = [...current].filter((id) => !seenTrayRef.current!.has(id));
    seenTrayRef.current = current;
    setTrayNewIds((previous) => {
      const next = new Set([...previous].filter((id) => current.has(id)));
      for (const id of arrivals) next.add(id);
      return next;
    });
    if (arrivals.length && canAnimateDesk(motion)) {
      setTrayEnteringIds(new Set(arrivals));
      const timer = window.setTimeout(() => setTrayEnteringIds(new Set()), 750);
      return () => window.clearTimeout(timer);
    }
    // trayItems is captured through trayIdsKey, its stable identity string.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trayIdsKey, motion, traySourcesSettled]);
  useFlip(trayCardsRef, trayIdsKey);

  /* ----- Masthead inputs ----- */
  const mastheadRun = latestFailed ?? latestCompleted;
  const mastheadResults = featuredResults.data ?? null;
  const mastheadVerdict = mastheadResults ? obj(mastheadResults.report.payload).market_verdict : null;
  const verdictKey = mastheadVerdict && typeof obj(mastheadVerdict).verdict === "string" ? strOf(obj(mastheadVerdict).verdict) : null;
  const voices = mastheadResults ? voicesOf(mastheadResults) : [];
  const firstRunInProgress = !mastheadRun && activeRuns.length > 0;

  const openCommandMenu = () => {
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }));
  };

  const header = <div className="desk-heading">
    <h1 className="font-h1-workspace">Home</h1>
    <div className="desk-heading-actions">
      <button type="button" className="secondary-button" onClick={openCommandMenu}>
        Start a test · Go to… <kbd className="kbd">⌘K</kbd>
      </button>
      {writable && applications.length > 0 ? <Link className="primary-button" to={newTestPath}>+ New test</Link> : null}
    </div>
  </div>;

  /* ----- Section builders ----- */

  const outcomeBar = (results: RunResults, run: TestRun) => {
    const outcomes = contractOutcomes(obj(results.report.payload));
    if (!outcomes) {
      const line = runOutcomeLine(results);
      return line ? <p className="desk-outcome-line">{line}</p> : null;
    }
    const total = outcomes.worked + outcomes.broken + outcomes.could_not_check + outcomes.not_checked;
    if (total === 0) return null;
    const segments: { key: DeskOutcome; word: string; count: number; tone: string }[] = [
      { key: "worked", word: "Worked", count: outcomes.worked, tone: "works" },
      { key: "broken", word: "Broken", count: outcomes.broken, tone: "broken" },
      { key: "could_not_check", word: "Could not check", count: outcomes.could_not_check, tone: "couldnot" },
      ...(outcomes.not_checked ? [{ key: "not_checked" as DeskOutcome, word: "Not checked", count: outcomes.not_checked, tone: "notchecked" }] : []),
    ];
    return <div className="desk-outcome-bar" role="group" aria-label="Journey outcomes">
      {segments.filter((segment) => segment.count > 0).map((segment) => (
        <Link
          key={segment.key}
          className="desk-outcome-segment"
          style={{ flexGrow: segment.count }}
          to={`/runs/${run.id}/results?outcome=${segment.key}`}
        >
          <DeskScaleFill frac={segment.count / total} className={`desk-outcome-fill tone-${segment.tone}`} />
          <span className="desk-outcome-label">
            <span className="desk-outcome-count">{segment.count}</span> {segment.word}
          </span>
        </Link>
      ))}
    </div>;
  };

  const masthead = (compact: boolean) => {
    if (!mastheadRun) return null;
    if (latestFailed) {
      // State G: a failed run is not a verdict on the app.
      const previous = previousCompleted && mastheadResults
        ? { run: previousCompleted, results: mastheadResults } : null;
      const previousVerdict = previous ? obj(previous.results.report.payload).market_verdict : null;
      const previousWord = previousVerdict && typeof obj(previousVerdict).verdict === "string"
        ? marketVerdictWord(strOf(obj(previousVerdict).verdict)) : null;
      return <section className="desk-masthead desk-masthead-failed" aria-labelledby="desk-masthead-heading">
        <DeskSwap swapKey={`${latestFailed.id}|failed`}>
          <p className="desk-eyebrow">LATEST RUN — {appName(latestFailed).toUpperCase()} · {testReference(latestFailed)}</p>
          <h2 id="desk-masthead-heading" className="desk-verdict-word">Latest run failed</h2>
          {latestFailed.status_reason ? <p className="desk-basis">{latestFailed.status_reason}</p> : null}
          {previous ? <p className="desk-previous">
            Previous result — {appName(previous.run)}: {previousWord ? <strong>{previousWord}</strong> : null}
            {previous.results.report.generated_at ? <> · Finished {formatDate(previous.results.report.generated_at)}</> : null}{" "}
            <Link className="text-link" to={`/runs/${previous.run.id}/results`}>Read the full result →</Link>
          </p> : null}
        </DeskSwap>
      </section>;
    }
    const run = latestCompleted!;
    const results = featuredResults.data ?? null;
    const finishedLabel = results?.report.generated_at ? formatDate(results.report.generated_at) : null;
    return <section className={`desk-masthead${verdictKey === "ready" ? " desk-masthead-ready" : ""}${compact ? " desk-masthead-compact" : ""}`} aria-labelledby="desk-masthead-heading">
      <DeskSwap swapKey={`${run.id}|${results ? (verdictKey ?? "legacy") : "pending"}`}>
      <p className="desk-eyebrow">LATEST RESULT — {appName(run).toUpperCase()}{finishedLabel ? ` · FINISHED ${finishedLabel.toUpperCase()}` : ""} · {testReference(run)}</p>
      {results ? <>
        {verdictKey ? <h2 id="desk-masthead-heading" className="desk-verdict-word">{marketVerdictWord(verdictKey)}</h2>
          : <h2 id="desk-masthead-heading" className="desk-verdict-word">{testTitle(run)}</h2>}
        {outcomeBar(results, run)}
        {results.report.executive_summary ? <p className="desk-basis">
          {truncateWords(results.report.executive_summary, 140)}{" "}
          <Link className="text-link" to={`/runs/${run.id}/results`}>Read the full result →</Link>
        </p> : <p className="desk-basis">
          <Link className="text-link" to={`/runs/${run.id}/results`}>Read the full result →</Link>
        </p>}
        {(() => {
          const evidence = evidenceOf(results, verdictKey, voices);
          return evidence ? <div className="desk-evidence">
            <p className="desk-evidence-title">{evidence.title}</p>
            <p className="desk-evidence-detail">{evidence.detail}</p>
          </div> : null;
        })()}
      </> : <>
        <h2 id="desk-masthead-heading" className="desk-verdict-word">{testTitle(run)}</h2>
        <p className="desk-basis">The report for this test is still being written.</p>
      </>}
      </DeskSwap>
    </section>;
  };

  const cardMotionProps = (item: TrayItem) => {
    const itemKey = trayItemKey(item);
    const entering = trayEnteringIds.has(itemKey);
    return {
      "data-flip-key": itemKey,
      ...(entering ? { "data-desk-enter": "" } : {}),
      className: `desk-speech-card${trayNewIds.has(itemKey) ? " desk-card-new" : ""}${entering ? " desk-enter desk-enter-lift" : ""}`,
    };
  };

  const tray = <section className="desk-tray" aria-labelledby="desk-tray-heading">
    {blocked ? <>
      <h2 id="desk-tray-heading" className="desk-section-label">NEEDS YOU — {trayItems.length}</h2>
      <div className="desk-tray-cards" ref={trayCardsRef} aria-live="polite">
        {trayItems.map((item) => {
          if (item.kind === "human") {
            const { run, action } = item;
            return <article key={`human-${action.id}`} {...cardMotionProps(item)}>
              <p className="desk-card-eyebrow">THE LEAD AGENT · ON {(action.journey_title ?? "A JOURNEY").toUpperCase()} · {appName(run).toUpperCase()}</p>
              <blockquote className="desk-card-quote">{action.instructions ?? "The tester is paused and needs your help."}</blockquote>
              <p className="desk-card-context">
                {action.requested_by_step_id ? `Tester paused at step ${action.requested_by_step_id}` : "Tester paused"}
                {action.expires_at ? ` · Request expires ${new Date(action.expires_at).toLocaleString()}` : ""}
              </p>
              <Link className="primary-button" to={`/runs/${run.id}/human-action`}>Help now →</Link>
            </article>;
          }
          if (item.kind === "approval") {
            const { run } = item;
            return <article key={`approval-${run.id}`} {...cardMotionProps(item)}>
              <p className="desk-card-eyebrow">TEST PLAN · {appName(run).toUpperCase()}</p>
              <p className="desk-card-quote">{testTitle(run)} — the tests are ready for your approval.</p>
              <Link className="primary-button" to={`/runs/${run.id}/contract`}>Review the tests →</Link>
            </article>;
          }
          return <article key={`knowledge-${item.id}`} {...cardMotionProps(item)}>
            <p className="desk-card-eyebrow">KNOWLEDGE · {item.sourceName.toUpperCase()}</p>
            <p className="desk-card-quote">{item.name} is ready for review.</p>
            <Link className="primary-button" to={`/knowledge/review/${item.id}`}>Review knowledge →</Link>
          </article>;
        })}
      </div>
    </> : <p className="desk-calm" id="desk-tray-heading">Nothing needs you.</p>}
  </section>;

  const stripUpdatedAt = stripQueries.reduce((max, query) => Math.max(max, query.dataUpdatedAt ?? 0), 0);
  const liveStrip = (promoted: boolean) => <section className={`desk-strip${promoted ? " desk-strip-promoted" : ""}`} aria-labelledby="desk-strip-heading">
    <div className="desk-strip-head">
      <h2 id="desk-strip-heading" className="desk-section-label">{promoted ? "YOUR TEST IS UNDER WAY" : "ON THE DESK NOW"}</h2>
      {stripUpdatedAt ? <span className="desk-updated">LAST UPDATED {new Date(stripUpdatedAt).toLocaleTimeString()}</span> : null}
    </div>
    {activeRuns.slice(0, 3).map((run, index) => {
      const journeys = stripQueries[index]?.data ?? [];
      const done = journeys.filter((journey) => journey.execution_status === "completed").length;
      const steps = journeys.reduce((sum, journey) => sum + (journey.step_count ?? 0), 0);
      const maxSteps = Math.max(1, ...journeys.map((journey) => journey.step_count ?? 0));
      const word = statusEntry("run", run.status)?.word ?? run.status;
      return <article className="desk-strip-run" key={run.id}>
        <p className="desk-strip-run-head">
          <span className={`desk-dot tone-${statusEntry("run", run.status)?.tone ?? "neutral"}`} aria-hidden="true" />
          <strong>{word}</strong> · <Link to={`/runs/${run.id}/overview`}>{testTitle(run)}</Link> · {appName(run)}
          {run.status === "running" ? <Link className="text-link" to={`/runs/${run.id}/watch`}>Watch live →</Link> : null}
        </p>
        {run.status_reason ? <p className="desk-strip-counts" style={{ margin: "0 0 8px" }}>{run.status_reason}</p> : null}
        {journeys.length ? <>
          <div className="desk-step-bars">
            {journeys.map((journey: JourneyExecution) => (
              <div className="desk-step-row" key={journey.id}>
                <span className="desk-step-name">{journey.persona_name}</span>
                <span className="desk-step-track"><span className="desk-step-fill" style={{ transform: `scaleX(${Math.max(4, ((journey.step_count ?? 0) / maxSteps) * 100) / 100})` }} /></span>
                <span className="desk-step-count">{journey.step_count ?? 0} steps</span>
              </div>
            ))}
          </div>
          <p className="desk-strip-counts">{done} of {journeys.length} {journeys.length === 1 ? "journey" : "journeys"} finished · {steps} steps recorded so far</p>
        </> : <p className="desk-strip-counts">No journeys recorded yet.</p>}
      </article>;
    })}
    {activeRuns.length > 3 ? <Link className="text-link" to="/runs">View all {activeRuns.length} active tests →</Link> : null}
  </section>;

  const voicesSection = voices.length && !latestFailed ? <section className="desk-voices contract-feeling-band" aria-labelledby="desk-voices-heading">
    <h2 id="desk-voices-heading" className="desk-section-label">VOICES</h2>
    {voices.map((voice) => (
      <VoiceCard key={`${voice.name}-${voice.quote.slice(0, 24)}`} name={voice.name} quote={voice.quote} />
    ))}
  </section> : null;

  const appsRail = <section className="desk-apps" aria-labelledby="desk-apps-heading">
    <div className="desk-strip-head">
      <h2 id="desk-apps-heading" className="desk-section-label">YOUR APPS</h2>
      {writable ? <Link className="text-link" to="/applications/new">Add an app</Link> : null}
    </div>
    {applications.map((app: Application) => (
      <article className="desk-app-row" key={app.id}>
        <span className="desk-app-tile" style={{ background: tileTint(app.id) }} aria-hidden="true">{app.name.charAt(0).toUpperCase()}</span>
        <div className="desk-app-copy">
          <h3 className="font-h3"><Link to={`/applications/${app.id}`}>{app.name}</Link></h3>
          {app.description ? <p className="font-body-small">{app.description}</p> : null}
          {app.latest_run_summary && (app.latest_run_summary.verdict || app.latest_run_summary.finished_at) ? (
            <p className="font-body-small">
              {app.latest_run_summary.verdict ? <strong>{marketVerdictWord(app.latest_run_summary.verdict)}</strong> : null}
              {app.latest_run_summary.verdict && app.latest_run_summary.finished_at ? " · " : null}
              {app.latest_run_summary.finished_at ? <>Finished {formatDate(app.latest_run_summary.finished_at)}</> : null}
            </p>
          ) : null}
        </div>
        <Link className="text-link" to={`/applications/${app.id}`}>Open →</Link>
      </article>
    ))}
  </section>;

  const featuredIds = new Set([latestCompleted?.id, latestFailed?.id, previousCompleted?.id].filter(Boolean));
  const archiveRuns = finishedRuns.filter((test) => !featuredIds.has(test.id));
  const draftRuns = runs.filter((test) => test.status === "draft" && !isApprovedReplayDraft(test));
  const recentCounts = (status: RecentFilter) => finishedRuns.filter((test) => status === "all" || test.status === status).length;

  /* ----- Archive list motion — filter changes only (spec §4e). Exits
     fade at the exit duration, survivors FLIP at the move duration,
     entrances fade at the enter duration, no stagger. Poll-driven
     changes stay discrete: the FLIP gate deadline below is opened
     only by changeFilter, never by data. ----- */
  const rowsFor = (filter: RecentFilter): TestRun[] => {
    const base = archiveRuns
      .filter((test) => filter === "all" || test.status === filter)
      .slice(0, 5);
    return filter === "all" ? [...base, ...draftRuns] : base;
  };
  const [archiveExitRows, setArchiveExitRows] = useState<{ run: TestRun; index: number }[]>([]);
  const [archiveEnteringIds, setArchiveEnteringIds] = useState<ReadonlySet<string>>(new Set());
  const archiveTimersRef = useRef<number[]>([]);
  const changeFilter = (next: RecentFilter) => {
    if (next === recentFilter) return;
    for (const timer of archiveTimersRef.current) window.clearTimeout(timer);
    archiveTimersRef.current = [];
    setArchiveExitRows([]);
    setArchiveEnteringIds(new Set());
    if (canAnimateDesk(motion)) {
      const currentRows = rowsFor(recentFilter);
      const nextRows = rowsFor(next);
      const nextIds = new Set(nextRows.map((run) => run.id));
      const currentIds = new Set(currentRows.map((run) => run.id));
      const leaving = currentRows
        .map((run, index) => ({ run, index }))
        .filter(({ run }) => !nextIds.has(run.id));
      const entering = nextRows.filter((run) => !currentIds.has(run.id)).map((run) => run.id);
      archiveFlipGateRef.current = performance.now() + 400;
      if (leaving.length) {
        setArchiveExitRows(leaving);
        archiveTimersRef.current.push(window.setTimeout(() => setArchiveExitRows([]), 170));
      }
      if (entering.length) {
        setArchiveEnteringIds(new Set(entering));
        archiveTimersRef.current.push(window.setTimeout(() => setArchiveEnteringIds(new Set()), 320));
      }
    }
    setRecentFilter(next);
  };
  const visibleRows = rowsFor(recentFilter);
  const renderedArchiveRows: { run: TestRun; leaving: boolean }[] = visibleRows.map((run) => ({ run, leaving: false }));
  for (const { run, index } of archiveExitRows) {
    if (!visibleRows.some((row) => row.id === run.id)) {
      renderedArchiveRows.splice(Math.min(index, renderedArchiveRows.length), 0, { run, leaving: true });
    }
  }
  useFlip(archiveRowsRef, renderedArchiveRows.map(({ run }) => run.id).join("|"), archiveFlipGateRef);
  useDeskEnterFlip(deskRef, `${[...trayEnteringIds].join(",")}|${[...archiveEnteringIds].join(",")}`);

  const archiveRow = ({ run: test, leaving }: { run: TestRun; leaving: boolean }) => {
    const action = testDestination(test);
    const entering = archiveEnteringIds.has(test.id);
    return <article
      className={`desk-archive-row${leaving ? " desk-row-leaving" : ""}${entering ? " desk-enter" : ""}`}
      key={test.id}
      data-flip-key={test.id}
      {...(entering ? { "data-desk-enter": "" } : {})}
    >
      <div>
        <h3 className="font-h3">{testTitle(test)}</h3>
        <span key={test.status}><TestStatusBadge status={test.status} /></span>
        {test.status_reason ? <p className="font-body-small">{test.status_reason}</p> : null}
      </div>
      <Link className="text-link" to={action.to}>{action.label}</Link>
    </article>;
  };
  const archive = <section className="desk-archive" aria-labelledby="desk-archive-heading">
    <h2 id="desk-archive-heading" className="desk-section-label">RECENT TESTS</h2>
    {finishedRuns.length > 1 ? <SegmentedControl
      className="concept-live-filter"
      label="Filter recent tests"
      options={(["all", "completed", "failed", "cancelled"] as RecentFilter[])
        .filter((status) => status === "all" || recentCounts(status) > 0)
        .map((status) => ({
          value: status,
          label: status === "all" ? `All \u00b7 ${recentCounts("all")}` : `${statusEntry("run", status)?.word ?? status} \u00b7 ${recentCounts(status)}`,
        }))}
      value={recentFilter}
      onChange={changeFilter}
    /> : null}
    <div ref={archiveRowsRef}>
      {renderedArchiveRows.length ? renderedArchiveRows.map(archiveRow)
        : <p className="font-body-small">{recentFilter === "all" ? "No other tests to show." : `No ${statusEntry("run", recentFilter)?.word.toLowerCase() ?? recentFilter} tests to show.`}</p>}
    </div>
    <Link className="text-link" to="/runs">See all tests</Link>
  </section>;

  /* ----- Loading / error (below every hook, per the rules of hooks) ----- */

  if (state.isPending) return <div className="desk">
    <div className="desk-heading"><h1 className="font-h1-workspace">Home</h1></div>
    <LoadingPanel label="Loading home" />
  </div>;
  if (!state.data) return <ErrorPanel message={state.error?.message || "Could not load your home page."}
    action={<button className="secondary-button" onClick={() => void state.refetch()}>Try again</button>} />;

  /* ----- Page composition, per state ----- */

  const deskClass = `desk${documentHidden ? " desk-suspended" : ""}`;

  if (applications.length === 0) {
    // State A: welcome + a clearly labelled example of the briefing.
    const demo = CANONICAL_DEMO_DATA;
    return <DeskMotionContext.Provider value={motion}>
    <div className={deskClass}>
      {header}
      {state.isError ? <InlineAlert severity="warning" title="Could not refresh your home page" role="alert" action={<button className="text-link" onClick={() => void state.refetch()}>Try again</button>}>Showing the last loaded data.</InlineAlert> : null}
      <section className="desk-welcome">
        <h2 className="font-h2-marketing">Your briefing desk.</h2>
        <p className="font-body">Add an app and the Lead Agent will test it like a person would, then brief you here: what worked, what broke, and what it could not check.</p>
        {writable ? <Link className="primary-button" to="/applications/new">Add an app</Link>
          : <p>An owner or administrator can add an app.</p>}
      </section>
      <section className="desk-example" aria-labelledby="desk-example-heading">
        <p className="desk-example-label" id="desk-example-heading">EXAMPLE — HOW YOUR BRIEFING WILL LOOK</p>
        <p className="desk-eyebrow">LATEST RESULT — THREAD &amp; CO. · FINISHED {demo.testDateLabel.toUpperCase()}</p>
        <p className="desk-verdict-word">{demo.verdict.word}</p>
        <p className="desk-basis">{demo.verdict.reason}</p>
        <div className="desk-evidence">
          <p className="desk-evidence-title">{demo.problems[0].title}</p>
          <p className="desk-evidence-detail">{demo.problems[0].description} Reproduced in a fresh browser.</p>
        </div>
        <VoiceCard name={demo.testers.find((tester) => tester.id === demo.feelings[0].tester)?.name ?? "Maya"} quote={demo.feelings[0].quote} role={`Simulated tester · ${demo.feelings[0].task}`} />
      </section>
      <p className="desk-footer-line">MarketTwin only counts defects reproduced in a fresh browser.</p>
    </div>
    </DeskMotionContext.Provider>;
  }

  const showMasthead = Boolean(mastheadRun);
  const blockedLayout = blocked && showMasthead && trayItems.some((item) => item.kind === "human");
  return <DeskMotionContext.Provider value={motion}>
  <div className={deskClass} ref={deskRef}>
    {header}
    {state.isError ? <InlineAlert severity="warning" title="Could not refresh your home page" role="alert" action={<button className="text-link" onClick={() => void state.refetch()}>Try again</button>}>Showing the last loaded data.</InlineAlert> : null}
    {blockedLayout ? tray : null}
    <DeskZone show={blockedLayout}>{masthead(true)}</DeskZone>
    <DeskZone show={!blockedLayout && showMasthead}>{masthead(false)}</DeskZone>
    {!showMasthead && runs.length === 0 ? <section className="desk-welcome">
      <h2 className="font-h2-marketing">Ready when you are.</h2>
      <p className="font-body">Start a test and the Lead Agent will explore your app, check what it finds, and bring the result here.</p>
      {writable ? <Link className="primary-button" to={newTestPath}>Start first test</Link> : null}
    </section> : null}
    <DeskZone show={firstRunInProgress}>{liveStrip(true)}</DeskZone>
    {!blockedLayout ? tray : null}
    <DeskZone show={!firstRunInProgress && activeRuns.length > 0}>{liveStrip(false)}</DeskZone>
    {voicesSection}
    {appsRail}
    {runs.length ? archive : null}
    <p className="desk-footer-line">MarketTwin only counts defects reproduced in a fresh browser.</p>
  </div>
  </DeskMotionContext.Provider>;
}

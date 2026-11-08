import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";
import type { RunContext } from "../../layouts/RunLayout";
import { api, type ExecutionPause, type LiveExecution, type RunActivityItem } from "../../lib/api";
import { canAuthorizeTarget } from "../../lib/permissions";
import { terminalTestStatuses } from "../../lib/results";
import { testBrief, statusLabel } from "../../lib/format";
import { HumanActionPage } from "./HumanActionPage";
import { InlineAlert } from "../../components/ui/Feedback";
import { LoadMore } from "../../components/ui/Pagination";
import { LiveBrowserObserver } from "./LiveBrowserObserver";

export function RunActivityPage() {
  const { run, user, workspace, results } = useOutletContext<RunContext>();
  return <LiveExecutionWorkbench key={`${user.id}:${workspace.id}:${workspace.role}:${run.id}`} context={{ run, user, workspace, results }} />;
}

function LiveExecutionWorkbench({ context: { run, user, workspace, results } }: { context: Pick<RunContext, "run" | "user" | "workspace" | "results"> }) {
  const permitted = canAuthorizeTarget(workspace.role);
  const queryClient = useQueryClient();
  const liveKey = ["live-execution", user.id, workspace.id, workspace.role, run.id];
  const [selectedJourney, setSelectedJourney] = useState("active");
  const [filter, setFilter] = useState("all");
  const [history, setHistory] = useState<RunActivityItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [historyStarted, setHistoryStarted] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const metadata = useQuery({
    queryKey: liveKey,
    queryFn: ({ signal }) => api.getLiveExecution(run.id, undefined, signal),
    enabled: permitted, refetchInterval: 2000, refetchIntervalInBackground: false,
  });
  const journeys = useQuery({
    queryKey: ["live-journeys", user.id, workspace.id, run.id],
    queryFn: ({ signal }) => api.getRunJourneys(run.id, signal), refetchInterval: 3000,
  });
  useEffect(() => {
    if (!historyStarted) setCursor(metadata.data?.activity.next_cursor ?? null);
  }, [metadata.data?.activity.next_cursor, historyStarted]);
  const events = [...new Map([...history, ...(metadata.data?.activity.items ?? [])].map((item) => [item.id, item])).values()]
    .sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at) || b.id.localeCompare(a.id));
  const selected = journeys.data?.find((item) => item.id === selectedJourney);
  const browser = metadata.isError || terminalTestStatuses.has(run.status)
    || (metadata.data && terminalTestStatuses.has(metadata.data.run_status)) ? null : metadata.data?.browser ?? null;
  const live = selectedJourney === "active" || browser?.journey_id === selectedJourney;
  const chosenBrowser = live ? browser : null;
  const pause = metadata.data?.pause;
  const actions = useQuery({
    queryKey: ["human-actions", user.id, workspace.id, run.id],
    queryFn: ({ signal }) => api.listHumanActions(run.id, signal), enabled: permitted,
    refetchInterval: 2500,
  });
  const linked = actions.data?.find((action) => action.id === pause?.human_request_id);
  const pendingPause = pause && ["requested", "quiescing", "paused", "resume_requested", "verifying"].includes(pause.status);
  const pauseSaved = (value: ExecutionPause) => {
    queryClient.setQueryData<LiveExecution>(liveKey, (previous) => previous ? { ...previous, pause: value } : previous);
    void queryClient.invalidateQueries({ queryKey: liveKey });
    void queryClient.invalidateQueries({ queryKey: ["human-actions", user.id, workspace.id, run.id] });
  };
  const requestPause = useMutation({ mutationFn: async () => {
    if (!browser) throw new Error("No browser is available for a pause request.");
    return api.requestExecutionPause(run.id, browser);
  }, onSuccess: pauseSaved });
  const resumePause = useMutation({ mutationFn: async () => {
    if (!pause) throw new Error("No acknowledged pause is available.");
    return api.resumeExecutionPause(run.id, pause.id);
  }, onSuccess: pauseSaved });
  // Watch grant (U-P3-02): a single-use observer ticket for the exact
  // browser + generation on screen. Re-granted when the browser
  // identity changes, and on demand when the stream asks to reconnect.
  const grant = useQuery({
    queryKey: ["live-grant", user.id, workspace.id, run.id, chosenBrowser?.browser_session_id, chosenBrowser?.generation],
    queryFn: ({ signal }) => api.getLiveGrant(run.id, chosenBrowser?.browser_session_id, signal),
    enabled: permitted && !metadata.isError && chosenBrowser?.viewer_state === "available",
    retry: false,
    staleTime: Infinity,
  });
  const stream = grant.data ? { url: grant.data.viewer_url, ticket: grant.data.ticket } : null;
  const reconnectStream = async () => {
    const fresh = await grant.refetch();
    if (!fresh.data) throw new Error("The live grant could not be renewed.");
    return { url: fresh.data.viewer_url, ticket: fresh.data.ticket };
  };
  const deep = run.configuration_snapshot.execution_mode === "deep_feature_v1";
  const event = events.find((item) => item.id === selectedEvent);
  const visibleEvents = events.filter((item) => {
    if (selectedJourney !== "active" && item.journey_id !== selectedJourney) return false;
    if (filter === "all") return true;
    if (filter === "human") return ["human_assistance", "approval"].includes(item.source);
    if (filter === "browser") return ["browser_agent", "deterministic_case"].includes(item.source);
    return ["failed", "policy_blocked", "inconclusive", "unverified", "skipped", "expired"].includes(item.status);
  });
  async function loadHistory() {
    if (!cursor || loadingHistory) return;
    setLoadingHistory(true); setHistoryError(false); setHistoryStarted(true);
    try {
      const page = await api.getLiveExecution(run.id, cursor);
      setHistory((previous) => [...new Map([...previous, ...page.activity.items].map((item) => [item.id, item])).values()]);
      setCursor(page.activity.next_cursor);
    } catch { setHistoryError(true); } finally { setLoadingHistory(false); }
  }
  return <section className="live-execution" aria-labelledby="live-execution-heading">
    <header className="live-execution-heading"><div><p className="section-label">Recorded state · {deep ? "Feature cases" : run.configuration_snapshot.execution_mode === "discovery_contract_v1" ? "Approved journeys and checks" : "Simulated tester journeys"}</p>
      <h2 id="live-execution-heading">{run.status === "running" || run.status === "awaiting_human" ? "Watch live" : "Watch"}</h2><p>{testBrief(run.configuration_snapshot)}</p></div>
      <div><strong>{statusLabel(metadata.data?.run_status ?? run.status)}</strong>
        {run.status === "completed" ? <p>{results.status === "ready" ? <Link to={`/runs/${run.id}/results`}>See test results</Link> : "Execution finished; evaluation/report still processing."}</p> : null}</div>
    </header>
    {metadata.isError ? <InlineAlert severity="warning" title="Live execution status is unavailable" role="alert" action={<button className="text-link" onClick={() => void metadata.refetch()}>Retry status</button>}>Recorded evidence remains available.</InlineAlert> : null}
    <div className="live-workbench">
      <aside className="live-work-selector" aria-label="Test work">
        <div className="live-work-choice"><label htmlFor="live-work">{deep ? "Case to inspect" : "Journey to inspect"}</label>
        <select id="live-work" className="text-input" value={selectedJourney} onChange={(e) => { setSelectedJourney(e.target.value); setSelectedEvent(null); }}>
          <option value="active">Follow active execution</option>
          {journeys.data?.map((item) => <option key={item.id} value={item.id}>{deep ? `Case ${item.ordinal}` : item.persona_name} · {item.mission_title}</option>)}
        </select>
        </div><div className="live-selected-work">
        {journeys.isError ? <InlineAlert severity="error" title="Journey selection could not be loaded" role="alert" /> : null}
        <p>{chosenBrowser?.journey_title ?? selected?.mission_title ?? "Waiting for recorded execution"}</p>
        {selected ? <><p>{selected.mission_objective}</p><dl className="definition-list"><div><dt>Execution</dt><dd>{selected.execution_status ? statusLabel(selected.execution_status) : "Not started"}</dd></div><div><dt>Outcome</dt><dd>{selected.outcome ? statusLabel(selected.outcome) : "Not recorded"}</dd></div></dl></> : null}
        <details><summary>Mode and tester context</summary><p className="muted">{deep ? "Feature cases use recorded browser actions and checks." : "Simulated testers are hypothetical testing perspectives, not human participants. Journeys run one at a time."}</p><Link className="text-link" to={`/runs/${run.id}/agents`}>Testers, goals and advanced settings</Link></details>
        </div>
      </aside>
      <div className="live-browser-column">
        <div className="section-heading"><h3>{live ? "Actual test browser" : "Recorded journey"}</h3><span>{run.status === "awaiting_human" ? <a className="text-link" href="#human-action-heading">Human assistance required — Assist</a> : live ? chosenBrowser?.viewer_state === "available" ? "Read only" : "Protected / unavailable" : "Historical evidence"}</span></div>
        <p className="muted">Live observation is read-only. Choose a recorded journey to inspect saved evidence.</p>
        {permitted && live ? <section className="live-pause-controls" aria-label="Execution pause">
          <button type="button" className="secondary-button" disabled={!browser || browser.control_state !== "agent" || Boolean(pendingPause) || requestPause.isPending || metadata.isError} onClick={() => requestPause.mutate()}>Request pause</button>
          {pause?.status === "paused" && linked?.status === "pending" && browser?.control_state === "human_pending" ? <button type="button" className="primary-button" disabled={resumePause.isPending} onClick={() => resumePause.mutate()}>Hand back</button> : null}
          <p role="status" aria-label="Manual pause status">{pause?.status === "requested" || pause?.status === "quiescing" ? "Pause requested; waiting for the current action to reach a safe boundary." : pause?.status === "paused" ? "Execution paused at a safe boundary. You can resume or take browser control below." : pause?.status === "resume_requested" || pause?.status === "verifying" ? "Resume requested; the worker is checking safe continuation." : pause ? `Pause ${pause.status.replaceAll("_", " ")}.` : "A pause is cooperative: it does not interrupt or replay an action already in flight."}</p>
          {pause && pendingPause ? <p className="muted">Pause expires <time dateTime={pause.expires_at}>{new Date(pause.expires_at).toLocaleTimeString()}</time>.</p> : null}
          {requestPause.isError || resumePause.isError ? <InlineAlert severity="error" title="The pause transition could not be confirmed" role="alert">Refresh status before trying again; no action is replayed.</InlineAlert> : null}
        </section> : null}
        {chosenBrowser?.board_item ? <p className="live-board-banner" role="status">Item {chosenBrowser.board_item.index} of {chosenBrowser.board_item.total} — {chosenBrowser.board_item.label}</p> : null}
        {!live && selected ? <section className="live-browser-empty"><h3>Historical evidence, not a live browser</h3><p>This journey has {selected.step_count} recorded steps and {selected.artifact_count} artifacts. Nothing from another browser is shown here.</p><Link className="primary-button" to={`/runs/${run.id}/journeys/${selected.id}`}>Inspect recorded steps and evidence</Link></section> : <LiveBrowserObserver runId={run.id} browser={chosenBrowser} identity={`${user.id}:${workspace.id}:${workspace.role}`} permitted={permitted && !metadata.isError} stream={stream} onReconnect={reconnectStream} />}
        <HumanActionPage />
        {chosenBrowser ? <details><summary>Browser identity</summary><dl className="definition-list"><div><dt>Session</dt><dd className="monospace">{chosenBrowser.browser_session_id}</dd></div><div><dt>Generation</dt><dd>{chosenBrowser.generation}</dd></div><div><dt>Executor</dt><dd>{chosenBrowser.requesting_agent}</dd></div></dl></details> : null}
      </div>
      <section className="live-activity" aria-labelledby="recorded-activity-heading">
        <h3 id="recorded-activity-heading">Recorded activity</h3>
        <label htmlFor="activity-filter" className="visually-hidden">Activity filter</label><select id="activity-filter" className="text-input" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="all">All activity</option><option value="problems">Problems</option><option value="human">Human needed</option><option value="browser">Browser actions</option></select>
        {!permitted ? <p>Live activity and browser observation require owner or administrator access. Your recorded journey access is unchanged.</p> : metadata.isPending ? <p role="status">Loading recorded execution…</p> : !visibleEvents.length ? <p>{terminalTestStatuses.has(run.status) ? "No further recorded action." : "No further recorded action yet."}</p> : <ol className="live-activity-list mt-timeline">{visibleEvents.map((item) => <li key={item.id}><button type="button" className="mt-timeline-row" aria-pressed={selectedEvent === item.id} onClick={() => setSelectedEvent(item.id)}><time className="mt-timeline-time" dateTime={item.occurred_at} title={new Date(item.occurred_at).toLocaleString()}>{new Date(item.occurred_at).toLocaleTimeString()}</time><strong className="mt-timeline-title">{item.title}</strong><span className="mt-timeline-meta">{statusLabel(item.status)} · {statusLabel(item.source)}</span></button></li>)}</ol>}
        {cursor ? <LoadMore noun="activity" loaded={events.length} loading={loadingHistory} onLoad={() => void loadHistory()} /> : null}
        {historyError ? <InlineAlert severity="error" title="Older activity could not be loaded" role="alert">Retry without changing execution.</InlineAlert> : null}
        {event ? <section className="live-step-inspector" aria-label="Selected activity"><h4>{event.title}</h4><p>{statusLabel(event.status)}. This is a recorded execution fact; it does not by itself establish a product defect.</p><p>Source: {statusLabel(event.source)}</p>{event.journey_id ? <Link className="text-link" to={`/runs/${run.id}/journeys/${event.journey_id}${event.step_id ? `?step=${event.step_id}` : ""}`}>Inspect {event.step_id ? `step ${event.step_id} and supporting evidence` : "journey evidence"}</Link> : null}</section> : null}
      </section>
    </div>
  </section>;
}

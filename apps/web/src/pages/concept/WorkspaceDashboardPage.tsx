import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";
import type { AppShellContext } from "../../layouts/AppShell";
import { api, type RunResults, type TestRun } from "../../lib/api";
import { testTitle } from "../../lib/format";
import { statusEntry } from "../../lib/status";
import { canWriteWorkspace } from "../../lib/permissions";
import { useWorkspaceTests } from "../../lib/useWorkspaceTests";
import { ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { TestStatusBadge } from "../../components/ui/StatusBadge";

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
  if (["planning", "queued", "running"].includes(test.status)) {
    return { to: `${base}/watch`, label: "Watch live" };
  }
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

type RecentFilter = "all" | "completed" | "failed" | "cancelled";

export function WorkspaceDashboardPage() {
  const { user, workspace } = useOutletContext<AppShellContext>();
  const state = useWorkspaceTests(user.id, workspace.id);
  const writable = canWriteWorkspace(workspace.role);
  const [recentFilter, setRecentFilter] = useState<RecentFilter>("all");
  const runs = [...(state.data?.runs ?? [])].sort((a, b) => (Date.parse(b.created_at ?? "") || 0) - (Date.parse(a.created_at ?? "") || 0));
  const needsYou = runs.filter(test => isApprovedReplayDraft(test) || test.status === "awaiting_human" || test.configuration_snapshot.discovery_stage === "awaiting_approval");
  const awaitingHuman = runs.filter(test => test.status === "awaiting_human");
  const oldestAwaitingHuman = awaitingHuman[awaitingHuman.length - 1];
  const active = runs.filter(test => ["planning", "queued", "running"].includes(test.status));
  const finished = runs.filter(test => ["completed", "failed", "cancelled"].includes(test.status));
  const featuredActive = active[0];
  const featuredFinished = finished.find(test => test.status === "completed");
  // Home fetches detail for exactly three featured runs — the parked run's
  // real request, the active run's real journey tally, the latest finished
  // run's real outcome. Lists never fan out per row (research notes,
  // patterns 3/6; backend gap BG-1).
  const humanActions = useQuery({
    queryKey: ["home-human-actions", user.id, workspace.id, oldestAwaitingHuman?.id],
    queryFn: ({ signal }) => api.listHumanActions(oldestAwaitingHuman!.id, signal),
    enabled: Boolean(oldestAwaitingHuman),
  });
  const activeJourneys = useQuery({
    queryKey: ["home-active-journeys", user.id, workspace.id, featuredActive?.id],
    queryFn: ({ signal }) => api.getRunJourneys(featuredActive!.id, signal),
    enabled: Boolean(featuredActive),
    refetchInterval: 5_000,
  });
  const featuredResults = useQuery({
    queryKey: ["home-featured-results", user.id, workspace.id, featuredFinished?.id],
    queryFn: ({ signal }) => api.getRunResults(featuredFinished!.id, signal),
    enabled: Boolean(featuredFinished),
    retry: false,
  });
  if (state.isPending) return <div className="concept-live-dashboard">
    <div className="concept-live-heading"><h1 className="font-h1-workspace">Home</h1></div>
    <LoadingPanel label="Loading home" />
  </div>;
  if (!state.data) return <ErrorPanel message={state.error?.message || "Could not load your home page."}
    action={<button className="secondary-button" onClick={() => void state.refetch()}>Try again</button>} />;
  const { applications } = state.data;
  const drafts = runs.filter(test => test.status === "draft" && !isApprovedReplayDraft(test));
  const newTestPath = applications.length === 1 ? `/applications/${applications[0].id}/runs/new` : "/applications";
  // The featured needs-you card and the section's rows must never show the
  // same run twice (Hallmark signed-in SI-8).
  const restNeedsYou = needsYou.filter(test => test.id !== oldestAwaitingHuman?.id);
  const pendingAction = humanActions.data?.find(action => action.status === "pending") ?? humanActions.data?.[0];
  const journeyTally = activeJourneys.data?.length ? {
    journeys: activeJourneys.data.length,
    steps: activeJourneys.data.reduce((sum, journey) => sum + (journey.step_count ?? 0), 0),
    done: activeJourneys.data.filter(journey => journey.execution_status === "completed").length,
  } : null;
  const outcomeLine = featuredResults.data ? runOutcomeLine(featuredResults.data) : null;
  const reportSummary = featuredResults.data?.report.executive_summary ?? null;
  // The state snapshot (research pattern 2): a colleague's catch-up in one
  // breath, composed only from data this page has actually loaded. A clause
  // renders only when its data exists.
  const snapshot: string[] = [];
  if (needsYou.length) {
    snapshot.push(oldestAwaitingHuman
      ? `${testTitle(oldestAwaitingHuman)} is waiting for you${needsYou.length > 1 ? ` — ${needsYou.length} tests need your help in all` : ""}.`
      : `${needsYou.length} ${needsYou.length === 1 ? "test needs" : "tests need"} your help.`);
  } else if (applications.length) {
    snapshot.push("Nothing needs you right now.");
  }
  if (featuredActive) {
    const word = statusEntry("run", featuredActive.status)?.word.toLowerCase() ?? featuredActive.status;
    snapshot.push(active.length === 1
      ? `${testTitle(featuredActive)} is ${word}${journeyTally ? ` — ${journeyTally.journeys} ${journeyTally.journeys === 1 ? "journey" : "journeys"}, ${journeyTally.steps} steps recorded so far` : ""}.`
      : `${active.length} tests are in progress; the newest is ${testTitle(featuredActive)}.`);
  }
  if (featuredFinished) {
    snapshot.push(outcomeLine
      ? `Latest result: ${testTitle(featuredFinished)} — ${outcomeLine}.`
      : `The latest finished test is ${testTitle(featuredFinished)}.`);
  }
  if (applications.length && !runs.length) {
    snapshot.push("No tests yet — start one and Home will keep you posted.");
  }
  const appRunSummary = (applicationId: string) => {
    const appRuns = runs.filter(test => test.application_id === applicationId);
    const parts = [`${appRuns.length} ${appRuns.length === 1 ? "test" : "tests"}`];
    const appActive = appRuns.filter(test => ["planning", "queued", "running"].includes(test.status)).length;
    if (appActive) parts.push(`${appActive} in progress`);
    const appNeedsYou = appRuns.filter(test => test.status === "awaiting_human").length;
    if (appNeedsYou) parts.push(`${appNeedsYou} needs you`);
    return parts.join(" · ");
  };
  const rows = (tests: TestRun[]) => tests.map(test => {
    const action = testDestination(test);
    return <article className="concept-live-row" key={test.id}>
      <div><h3 className="font-h3">{testTitle(test)}</h3>
        {/* Keyed by status: when a refetch changes it, the pill remounts and
            the change pulse fires once (HR-3). */}
        <span key={test.status} className="mt-change"><TestStatusBadge status={test.status} /></span>
        {test.status_reason ? <p className="font-body-small">{test.status_reason}</p> : null}</div>
      <Link className="text-link" to={action.to}>{action.label}</Link>
    </article>;
  });
  const recentVisible = finished
    .filter(test => test.id !== featuredFinished?.id)
    .filter(test => recentFilter === "all" || test.status === recentFilter)
    .slice(0, 5);
  const recentCounts = (status: RecentFilter) => finished.filter(test => status === "all" || test.status === status).length;
  return <div className="concept-live-dashboard">
    <div className="concept-live-heading"><h1 className="font-h1-workspace">Home</h1>
      {writable && applications.length > 0 ? <Link className="primary-button" to={newTestPath}>Start a test</Link> : null}</div>
    {state.isError ? <p role="alert">Could not refresh your home page. Showing the last loaded data. <button className="text-link" onClick={() => void state.refetch()}>Try again</button></p> : null}
    {applications.length === 0 ? <section className="concept-live-empty">
      <h2 className="font-h2-marketing">Your home will live here.</h2>
      <p className="font-body">Add an app and we will test it like a person would, then show you what worked, what broke, and what we could not check.</p>
      {writable ? <Link className="primary-button" to="/applications/new">Add an app</Link>
        : <p>An owner or administrator can add an app.</p>}
    </section> : <>
      {snapshot.length ? <p className="concept-live-snapshot font-body">{snapshot.join(" ")}</p> : null}
      <div className="concept-live-summary" role="group" aria-label="Workspace summary">
        <div className={`concept-live-stat${needsYou.length ? " is-alert" : ""}`}><span key={needsYou.length} className="font-stat-numeral mt-change">{needsYou.length}</span><span className="font-body-small">Needs your help</span></div>
        <div className="concept-live-stat"><span key={active.length} className="font-stat-numeral mt-change">{active.length}</span><span className="font-body-small">Happening now</span></div>
        <div className="concept-live-stat"><span key={applications.length} className="font-stat-numeral mt-change">{applications.length}</span><span className="font-body-small">Your apps</span></div>
        <div className="concept-live-stat"><span key={finished.length} className="font-stat-numeral mt-change">{finished.length}</span><span className="font-body-small">Recent tests</span></div>
      </div>
      <section className="concept-live-panel" aria-labelledby="dashboard-needs-you"><h2 id="dashboard-needs-you" className="font-h2-workspace">Needs your help</h2>
        {oldestAwaitingHuman ? <article className="concept-live-feature">
          <div><h3 className="font-h3">{testTitle(oldestAwaitingHuman)}</h3>
            <p className="font-body-small">Needs you — the tester is paused{oldestAwaitingHuman.status_reason ? ` · ${oldestAwaitingHuman.status_reason}` : ""}</p>
            {pendingAction?.instructions ? <p className="concept-live-ask font-body-small">
              <strong>{pendingAction.requesting_agent || "The tester"}</strong>
              {pendingAction.journey_title ? <> · {pendingAction.journey_title}</> : null}
              {" — "}{pendingAction.instructions}</p> : null}</div>
          <Link className="primary-button" to={testDestination(oldestAwaitingHuman).to}>{testDestination(oldestAwaitingHuman).label}</Link>
        </article> : null}
        {restNeedsYou.length ? rows(restNeedsYou) : needsYou.length ? null : <p className="font-body">Nothing needs you right now.</p>}</section>
      <section className="concept-live-panel" aria-labelledby="dashboard-happening"><h2 id="dashboard-happening" className="font-h2-workspace">Happening now</h2>
        {active.length ? <>
          {featuredActive && journeyTally ? <p className="concept-live-progress font-body-small" key={`${journeyTally.journeys}-${journeyTally.steps}-${journeyTally.done}`}>
            {testTitle(featuredActive)}: {journeyTally.done} of {journeyTally.journeys} {journeyTally.journeys === 1 ? "journey" : "journeys"} finished · {journeyTally.steps} steps recorded so far.</p> : null}
          {rows(active)}</> : <p className="font-body-small">No test is running right now.</p>}</section>
      <section className="concept-live-panel" aria-labelledby="dashboard-apps"><div className="concept-live-heading"><h2 id="dashboard-apps" className="font-h2-workspace">Your apps</h2>
        {writable ? <Link className="text-link" to="/applications/new">Add an app</Link> : null}</div>
        {applications.map(app => <article className="concept-live-row" key={app.id}>
          <div><h3 className="font-h3"><Link to={`/applications/${app.id}`}>{app.name}</Link></h3>
            {app.description ? <p className="font-body-small">{app.description}</p> : null}
            <p className="font-body-small">{appRunSummary(app.id)}</p></div>
          <Link className="text-link" to={`/applications/${app.id}/runs`}>See tests</Link>
        </article>)}</section>
      <section className="concept-live-panel" aria-labelledby="dashboard-results"><h2 id="dashboard-results" className="font-h2-workspace">Recent tests</h2>
        {featuredFinished ? <article className="concept-live-result">
          <div><h3 className="font-h3">{testTitle(featuredFinished)}</h3>
            <span key={featuredFinished.status} className="mt-change"><TestStatusBadge status={featuredFinished.status} /></span>
            {outcomeLine ? <p className="font-body">{outcomeLine}</p> : null}
            {reportSummary ? <details className="concept-live-more"><summary>What the test found</summary><p className="font-body-small">{reportSummary}</p></details> : null}</div>
          <Link className="text-link" to={testDestination(featuredFinished).to}>{testDestination(featuredFinished).label}</Link>
        </article> : null}
        {finished.length > 1 ? <div className="segmented-control concept-live-filter" role="group" aria-label="Filter recent tests">
          {(["all", "completed", "failed", "cancelled"] as RecentFilter[])
            .filter(status => status === "all" || recentCounts(status) > 0)
            .map(status => <button key={status} type="button" aria-pressed={recentFilter === status}
              className={`segmented-control-item${recentFilter === status ? " active" : ""}`}
              onClick={() => setRecentFilter(status)}>
              {status === "all" ? `All · ${recentCounts("all")}` : `${statusEntry("run", status)?.word ?? status} · ${recentCounts(status)}`}
            </button>)}
        </div> : null}
        {recentVisible.length ? rows(recentVisible) : finished.length ? <p className="font-body-small">{recentFilter === "all" ? "No other tests to show." : `No ${statusEntry("run", recentFilter)?.word.toLowerCase() ?? recentFilter} tests to show.`}</p> : <p className="font-body-small">Your test results will appear here.</p>}
        <Link className="text-link" to="/runs">See all tests</Link></section>
      {drafts.length ? <section className="concept-live-panel" aria-labelledby="dashboard-drafts"><h2 id="dashboard-drafts" className="font-h2-workspace">Draft tests</h2>{rows(drafts)}</section> : null}
    </>}
  </div>;
}

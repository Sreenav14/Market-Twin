import { Link, useOutletContext } from "react-router-dom";
import type { AppShellContext } from "../../layouts/AppShell";
import type { TestRun } from "../../lib/api";
import { testTitle } from "../../lib/format";
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

export function WorkspaceDashboardPage() {
  const { user, workspace } = useOutletContext<AppShellContext>();
  const state = useWorkspaceTests(user.id, workspace.id);
  const writable = canWriteWorkspace(workspace.role);
  if (state.isPending) return <LoadingPanel label="Loading dashboard" />;
  if (!state.data) return <ErrorPanel message={state.error?.message || "Could not load your dashboard."}
    action={<button className="secondary-button" onClick={() => void state.refetch()}>Try again</button>} />;
  const { applications } = state.data;
  const runs = [...state.data.runs].sort((a, b) => (Date.parse(b.created_at ?? "") || 0) - (Date.parse(a.created_at ?? "") || 0));
  const needsYou = runs.filter(test => isApprovedReplayDraft(test) || test.status === "awaiting_human" || test.configuration_snapshot.discovery_stage === "awaiting_approval");
  const drafts = runs.filter(test => test.status === "draft" && !isApprovedReplayDraft(test));
  const active = runs.filter(test => ["planning", "queued", "running"].includes(test.status));
  const finished = runs.filter(test => ["completed", "failed", "cancelled"].includes(test.status));
  const newTestPath = applications.length === 1 ? `/applications/${applications[0].id}/runs/new` : "/applications";
  const rows = (tests: TestRun[]) => tests.map(test => {
    const action = testDestination(test);
    return <article className="concept-live-row" key={test.id}>
      <div><h3 className="font-h3">{testTitle(test)}</h3><TestStatusBadge status={test.status} />
        {test.status_reason ? <p className="font-body-small">{test.status_reason}</p> : null}</div>
      <Link className="text-link" to={action.to}>{action.label} →</Link>
    </article>;
  });
  return <div className="concept-live-dashboard">
    <div className="concept-live-heading"><h1 className="font-h1-workspace">Dashboard</h1>
      {writable && applications.length > 0 ? <Link className="primary-button" to={newTestPath}>Start a test</Link> : null}</div>
    {state.isError ? <p role="alert">Could not refresh your dashboard. Showing the last loaded data. <button className="text-link" onClick={() => void state.refetch()}>Try again</button></p> : null}
    {applications.length === 0 ? <section className="concept-live-empty">
      <h2 className="font-h2-marketing">Your dashboard will live here.</h2>
      <p className="font-body">Add an app and we will test it like a person would — then show you what worked, what broke, and what we could not check.</p>
      {writable ? <Link className="primary-button" to="/applications/new">Add an app</Link>
        : <p>An owner or administrator can add an app.</p>}
    </section> : <>
      <section aria-labelledby="dashboard-needs-you"><h2 id="dashboard-needs-you" className="font-h2-workspace">Needs your help</h2>
        {needsYou.length ? rows(needsYou) : <p className="font-body">Nothing needs you right now.</p>}</section>
      <section aria-labelledby="dashboard-happening"><h2 id="dashboard-happening" className="font-h2-workspace">Happening now</h2>
        {active.length ? rows(active) : <p className="font-body-small">No test is running right now.</p>}</section>
      <section aria-labelledby="dashboard-apps"><div className="concept-live-heading"><h2 id="dashboard-apps" className="font-h2-workspace">Your apps</h2>
        {writable ? <Link className="text-link" to="/applications/new">Add an app →</Link> : null}</div>
        {applications.map(app => <article className="concept-live-row" key={app.id}>
          <div><h3 className="font-h3"><Link to={`/applications/${app.id}`}>{app.name}</Link></h3>
            {app.description ? <p className="font-body-small">{app.description}</p> : null}</div>
          <Link className="text-link" to={`/applications/${app.id}/runs`}>See tests →</Link>
        </article>)}</section>
      <section aria-labelledby="dashboard-results"><h2 id="dashboard-results" className="font-h2-workspace">Recent tests</h2>
        {finished.length ? rows(finished.slice(0, 5)) : <p className="font-body-small">Your test results will appear here.</p>}
        <Link className="text-link" to="/runs">See all tests →</Link></section>
      {drafts.length ? <section aria-labelledby="dashboard-drafts"><h2 id="dashboard-drafts" className="font-h2-workspace">Draft tests</h2>{rows(drafts)}</section> : null}
    </>}
  </div>;
}

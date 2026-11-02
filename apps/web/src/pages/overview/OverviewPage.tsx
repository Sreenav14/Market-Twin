import { Link, useOutletContext } from "react-router-dom";
import { ArrowUpRight, Plus } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { TestStatusBadge } from "../../components/ui/StatusBadge";
import { Button } from "../../components/ui/button";
import { canWriteWorkspace } from "../../lib/permissions";
import { useWorkspaceTests } from "../../lib/useWorkspaceTests";
import { testTitle, testReference, textValue } from "../../lib/format";
import { AppShellContext } from "../../layouts/AppShell";

export function OverviewPage() {
  const { workspace, user } = useOutletContext<AppShellContext>();
  const state = useWorkspaceTests(user.id, workspace.id);
  const canWrite = canWriteWorkspace(workspace.role);
  if (state.isPending) return <LoadingPanel label="Loading workspace" />;
  if (!state.data) return <ErrorPanel message={state.error?.message || "Could not load the workspace."}
    action={<Button variant="secondary" onClick={() => void state.refetch()}>Try again</Button>} />;

  const { applications, runs } = state.data;
  const awaitingHuman = runs.filter((run) => run.status === "awaiting_human");
  const active = runs.filter((run) => ["planning", "queued", "running"].includes(run.status));
  const featured = active[0] ?? runs.find((run) => run.status === "completed") ?? runs[0];
  const newTestPath = applications.length === 1
    ? `/applications/${applications[0].id}/runs/new` : "/applications";
  const actionFor = (run: typeof runs[number]) => run.status === "completed"
    ? { to: `/runs/${run.id}/report`, label: "Review report" }
    : run.status === "awaiting_human"
    ? { to: `/runs/${run.id}/human-action`, label: "Continue test" }
    : ["planning", "queued", "running"].includes(run.status)
    ? { to: `/runs/${run.id}/activity`, label: "Watch execution" }
    : { to: `/runs/${run.id}/overview`, label: run.status === "draft" ? "Review draft" : "View test" };

  return <>
    <PageHeader title="Workspace overview" description="Continue a test or review its recorded evidence."
      action={canWrite && applications.length > 0 ? <Link className="primary-button" to={newTestPath}>
        <Plus size={17} aria-hidden="true" />New test</Link> : undefined} />
    {state.isError ? <p className="inline-note" role="alert">
      Could not refresh tests. Showing the last loaded data.{" "}
      <Button variant="ghost" size="sm" onClick={() => void state.refetch()}>Try again</Button>
    </p> : null}
    {applications.length === 0 ? <EmptyState title="Add your first application"
      copy="Connect a target environment to start testing."
      action={canWrite ? <Link className="primary-button" to="/applications/new">Add application</Link> : undefined} /> : <>
      {awaitingHuman.length > 0 ? <section className="mt-overview-attention" aria-labelledby="awaiting-human-heading">
        <div className="section-heading"><h2 id="awaiting-human-heading">Awaiting your attention</h2>
          <span>{awaitingHuman.length} {awaitingHuman.length === 1 ? "test" : "tests"}</span></div>
        <div className="mt-attention-row-list">{awaitingHuman.map((run) => <Link className="mt-attention-row"
          to={`/runs/${run.id}/human-action`} key={run.id}>
          <span><strong>{testTitle(run)}</strong><small>{textValue(run.target_snapshot.name, "Target")}</small></span>
          <span>Continue test</span><ArrowUpRight size={18} aria-hidden="true" />
        </Link>)}</div>
      </section> : null}
      <p className="workspace-inventory">{applications.length} {applications.length === 1 ? "application" : "applications"}
        <span aria-hidden="true"> / </span>{runs.length} {runs.length === 1 ? "test" : "tests"}
        {active.length > 0 ? ` · ${active.length} in progress` : ""}</p>
      <nav className="overview-status-index" aria-label="Test inventory">
        <Link to="/runs"><span>All tests</span><strong>{runs.length}</strong><ArrowUpRight size={18} aria-hidden="true" /></Link>
        <Link to="/runs"><span>In progress</span><strong>{active.length}</strong><small>Planning, queued or running</small></Link>
        <Link to="/runs"><span>Execution completed</span><strong>{runs.filter(run => run.status === "completed").length}</strong><small>Review evidence for outcomes</small></Link>
      </nav>
      <div className="overview-workbench">
        <section aria-labelledby="test-activity-heading">
          <div className="section-heading"><h2 id="test-activity-heading">Test activity</h2>
            <Link className="text-link" to="/runs">All tests</Link></div>
          {featured ? <article className="overview-featured-test">
            <div className="section-heading"><span className="monospace">{testReference(featured)}</span>
              <TestStatusBadge status={featured.status} /></div>
            <h3>{textValue(featured.configuration_snapshot.test_name, "Untitled test")}</h3>
            <p className="featured-target">{textValue(featured.target_snapshot.name, "Target")}<span> / </span>{textValue(featured.target_snapshot.environment, "Environment unspecified")}</p>
            {typeof featured.configuration_snapshot.study_brief === "string" ?
              <div className="featured-objective"><span className="featured-field-label">Testing goal</span><p className="featured-goal">{featured.configuration_snapshot.study_brief}</p></div> : null}
            <div className="featured-test-action">
              <p>{featured.status === "completed" ? "Execution ended. Inspect the evidence before drawing a product conclusion."
                : featured.status === "draft" ? "This test has not started. Review its configuration before execution."
                : "Open the test to follow its current state and recorded activity."}</p>
              <Link className="primary-button" to={actionFor(featured).to}>{actionFor(featured).label}
                <ArrowUpRight size={16} aria-hidden="true" /></Link>
            </div>
          </article> : <EmptyState title="No tests yet" copy="Describe a user task you want to evaluate."
            action={canWrite ? <Link className="primary-button" to={newTestPath}>Create your first test</Link> : undefined} />}
          {runs.length > 1 ? <div className="study-table">{runs.filter((run) => run.id !== featured?.id).slice(0, 5).map((run) =>
            <Link className="study-row" to={actionFor(run).to} key={run.id}>
              <span className="study-row-copy"><strong>{testTitle(run)}</strong>
                <span>{textValue(run.target_snapshot.name, "Target")}</span></span>
              <TestStatusBadge status={run.status} /><ArrowUpRight size={18} aria-hidden="true" />
            </Link>)}</div> : null}
        </section>
        <aside className="overview-next-test" aria-labelledby="next-test-heading">
          <h2 id="next-test-heading">Create a test</h2>
          <p>Choose an authorized target and describe what a user should be able to do.</p>
          <dl><div><dt>Start with an outcome</dt><dd>Describe success, rather than a script of clicks.</dd></div>
            <div><dt>Keep the scope clear</dt><dd>Use an environment you are authorized to test.</dd></div></dl>
          {canWrite ? <Link className="secondary-button" to={newTestPath}>Set up a test<ArrowUpRight size={16} aria-hidden="true" /></Link>
            : <p className="muted">An owner or administrator can create tests.</p>}
        </aside>
      </div>
      <section className="overview-applications" aria-labelledby="overview-applications-heading">
        <div className="section-heading"><h2 id="overview-applications-heading">Applications</h2>
          <Link className="text-link" to="/applications">View all</Link></div>
        {applications.slice(0, 6).map((application) => <Link to={`/applications/${application.id}`}
          className="application-index-row" key={application.id}>
          <span className="product-icon small">{application.name.slice(0, 2).toUpperCase()}</span>
          <span><strong>{application.name}</strong><small>{application.status}</small></span>
          <ArrowUpRight size={16} aria-hidden="true" />
        </Link>)}
      </section>
    </>}
    <section className="overview-knowledge-tools" aria-label="Prepare knowledge for testing">
      <div><h2>Knowledge for tests <span className="muted">Optional</span></h2>
        <p className="muted">Add a source, review its draft, and attach approved knowledge to an application.</p></div>
      <div className="inline-actions"><Link className="text-link" to="/ingestion">Ingest knowledge</Link>
        <Link className="text-link" to="/knowledge/review">Review knowledge</Link></div>
    </section>
    <details className="mt-progressive-help"><summary>How tests work</summary>
      <p>Creating a test saves a draft. Start it when you are ready. Execution records browser steps; evaluation reviews their evidence.</p>
      <p>Execution status and product outcomes are separate. Simulated testers do not replace human research.</p>
    </details>
  </>;
}

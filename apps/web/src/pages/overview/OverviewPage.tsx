import { Link, useOutletContext } from "react-router-dom";
import { ArrowUpRight, Plus, FlaskConical } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { TestStatusBadge } from "../../components/ui/StatusBadge";
import { Button } from "../../components/ui/button";
import { canWriteWorkspace } from "../../lib/permissions";
import { useWorkspaceTests } from "../../lib/useWorkspaceTests";
import { testBrief, textValue } from "../../lib/format";
import { AppShellContext } from "../../layouts/AppShell";

export function OverviewPage() {
  const { workspace, user } = useOutletContext<AppShellContext>();
  const state = useWorkspaceTests(user.id, workspace.id);
  const canWrite = canWriteWorkspace(workspace.role);
  if (state.isPending) return <LoadingPanel label="Loading workspace" />;
  if (state.isError) return <ErrorPanel message={state.error.message} action={<Button variant="secondary" onClick={() => void state.refetch()}>Try again</Button>} />;
  const { applications, runs } = state.data;
  const completed = runs.filter(run => run.status === "completed");
  const active = runs.filter(run => ["planning", "queued", "running"].includes(run.status));
  return <><PageHeader title="Workspace overview" description="See how your app performs and what stands between users and its value." action={canWrite ? <Link className="primary-button" to={applications.length === 1 ? `/applications/${applications[0].id}/runs/new` : applications.length ? "/applications" : "/applications/new"}><Plus size={17} aria-hidden="true" />New test</Link> : undefined} />
    {applications.length === 0 ? <EmptyState title="Bring your first product into focus" copy="Add your app, connect a target, and test a real user task." action={canWrite ? <Link className="primary-button" to="/applications/new">Add application</Link> : undefined} /> : <>
      <dl className="workspace-metrics"><div><dt>Applications</dt><dd>{applications.length}</dd></div><div><dt>Tests created</dt><dd>{runs.length}</dd></div><div><dt>In progress</dt><dd>{active.length}<span className="metric-signal" aria-hidden="true" /></dd></div><div><dt>Completed</dt><dd>{completed.length}</dd></div></dl>
      <div className="overview-layout"><section><div className="section-heading"><h2>Test activity</h2><Link className="text-link" to="/runs">All tests</Link></div>{runs.length === 0 ? <div className="first-study"><FlaskConical size={30} aria-hidden="true" /><h3>Which experience should we test next?</h3><p>Test a key user task, find the friction, and review the evidence in one place.</p><Link className="secondary-button" to={applications.length === 1 ? `/applications/${applications[0].id}/runs/new` : "/applications"}>Create your first test</Link></div> : <div className="study-table">{runs.slice(0, 6).map(run => <Link className="study-row" to={`/runs/${run.id}/overview`} key={run.id}><span className="study-row-copy"><strong>{testBrief(run.configuration_snapshot)}</strong><span>{textValue(run.target_snapshot.name, "Target")}</span></span><TestStatusBadge status={run.status} /><ArrowUpRight size={18} aria-hidden="true" /></Link>)}</div>}</section>
      <aside className="application-index"><div className="section-heading"><h2>Applications</h2><Link className="text-link" to="/applications">View all</Link></div>{applications.slice(0, 6).map(application => <Link to={`/applications/${application.id}`} className="application-index-row" key={application.id}><span className="product-icon small">{application.name.slice(0, 2).toUpperCase()}</span><span><strong>{application.name}</strong><small>{application.status}</small></span><ArrowUpRight size={16} aria-hidden="true" /></Link>)}<p className="application-hint">Each application groups its targets, tests, and findings.</p></aside></div>
    </>}
  </>;
}

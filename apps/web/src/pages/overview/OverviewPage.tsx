import { Link, useOutletContext } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { Application, api } from "../../lib/api";
import { canWriteWorkspace, roleLabel } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function OverviewPage() {
  const { workspace } = useOutletContext<AppShellContext>();
  const applicationsState = useAsync(() => api.listApplications(workspace.id), [workspace.id]);
  const canWrite = canWriteWorkspace(workspace.role);
  if (applicationsState.status === "loading") return <LoadingPanel label="Loading overview" />;
  if (applicationsState.status === "error") return <ErrorPanel message={applicationsState.error} />;
  const applications: Application[] = applicationsState.data;
  return <><PageHeader eyebrow="Workspace" title="Overview" description="Configure authorized product targets, create studies, and review testing activity from one place." action={canWrite ? <Link className="primary-button" to={applications.length === 0 ? "/applications/new" : "/applications"}><Icon name="plus" size={16} /> Start a study</Link> : undefined} /><div className="metric-grid"><article className="metric-card"><span>Applications</span><strong>{applications.length}</strong><small>Products in this workspace</small></article><article className="metric-card"><span>Workspace</span><strong>{workspace.status}</strong><small>{roleLabel(workspace.role)}</small></article><article className="metric-card"><span>Perspectives</span><strong>Dynamic</strong><small>Generated for each study</small></article></div><section className="section-block" aria-labelledby="overview-applications"><div className="section-heading"><div><p className="eyebrow">Products</p><h2 id="overview-applications">Applications</h2></div><Link className="text-link" to="/applications">View all</Link></div>{applications.length === 0 ? <EmptyState title="Add your first application" copy="Applications group the product targets and studies your team evaluates." action={canWrite ? <Link className="primary-button" to="/applications/new">Add application</Link> : undefined} /> : <div className="card-grid">{applications.slice(0,4).map((application) => <Link className="product-card" to={`/applications/${application.id}`} key={application.id}><span className="product-icon">{application.name.slice(0,2).toUpperCase()}</span><div><strong>{application.name}</strong><p>{application.description || "No description yet."}</p></div><Icon name="arrow" size={16} /></Link>)}</div>}</section></>;
}

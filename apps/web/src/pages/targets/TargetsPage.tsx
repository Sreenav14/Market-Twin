import { Link, useOutletContext, useParams } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { api } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function TargetsPage() {
  const { applicationId = "" } = useParams(); const { workspace } = useOutletContext<AppShellContext>(); const appState = useAsync(() => api.getApplication(applicationId), [applicationId]); const targetsState = useAsync(() => api.listTargets(applicationId), [applicationId]);
  if (appState.status === "loading") return <LoadingPanel label="Loading application" />; if (appState.status === "error") return <ErrorPanel message={appState.error} />;
  const canWrite = canWriteWorkspace(workspace.role) && appState.data.status === "active";
  return <><PageHeader eyebrow={appState.data.name} title="Targets" description="Environments MarketTwin may test after explicit authorization." action={canWrite ? <Link className="primary-button" to={`/applications/${applicationId}/targets/new`}><Icon name="plus" size={16} /> Add target</Link> : undefined} />{targetsState.status === "loading" ? <LoadingPanel label="Loading targets" /> : targetsState.status === "error" ? <ErrorPanel message={targetsState.error} /> : targetsState.data.length === 0 ? <EmptyState title="No targets configured" copy="Add an environment before creating a study." action={canWrite ? <Link className="primary-button" to={`/applications/${applicationId}/targets/new`}>Add target</Link> : undefined} /> : <div className="data-list">{targetsState.data.map((target) => <Link className="data-row" to={`/targets/${target.id}`} key={target.id}><span className="row-icon"><Icon name="target" size={17} /></span><div className="row-primary"><strong>{target.name}</strong><span>{target.base_url}</span></div><span className="environment-label">{target.environment}</span><Icon name="arrow" size={16} /></Link>)}</div>}</>;
}

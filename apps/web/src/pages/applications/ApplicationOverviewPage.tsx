import { Link, useOutletContext, useParams } from "react-router-dom";

import { Icon } from "../../components/ui/Icon";
import { LifecyclePanel } from "../../components/ui/LifecyclePanel";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { api } from "../../lib/api";
import { studyBrief, textValue } from "../../lib/format";
import { canManageLifecycle, canWriteWorkspace } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function ApplicationOverviewPage() {
  const { applicationId = "" } = useParams();
  const { workspace } = useOutletContext<AppShellContext>();
  const appState = useAsync(() => api.getApplication(applicationId), [applicationId]);
  const targetsState = useAsync(() => api.listTargets(applicationId), [applicationId]);
  const runsState = useAsync(() => api.listRuns(applicationId), [applicationId]);
  const canWriteRole = canWriteWorkspace(workspace.role);

  if (appState.status === "loading") return <LoadingPanel label="Loading application" />;
  if (appState.status === "error") return <ErrorPanel message={appState.error} />;

  const application = appState.data;
  const canWrite = canWriteRole && application.status === "active";

  return (
    <>
      <PageHeader eyebrow="Application" title={application.name} description={application.description || "Configure authorized targets and run product studies against this application."} action={canWrite ? <Link className="primary-button" to={`/applications/${application.id}/runs/new`}><Icon name="plus" size={16} /> New study</Link> : undefined} />
      <div className="tab-strip" aria-label="Application sections"><span className="tab-link active">Overview</span><Link className="tab-link" to={`/applications/${application.id}/targets`}>Targets</Link><Link className="tab-link" to={`/applications/${application.id}/runs`}>Runs</Link></div>

      <section className="section-block" aria-labelledby="app-targets-heading">
        <div className="section-heading"><div><p className="eyebrow">Environments</p><h2 id="app-targets-heading">Targets</h2></div>{canWrite ? <Link className="secondary-button compact" to={`/applications/${application.id}/targets/new`}><Icon name="plus" size={14} /> Add target</Link> : null}</div>
        {targetsState.status === "loading" ? <LoadingPanel label="Loading targets" /> : targetsState.status === "error" ? <ErrorPanel message={targetsState.error} /> : targetsState.data.length === 0 ? <EmptyState title="No targets configured" copy="Add a local, staging, QA, demo, or production URL before creating a study." action={canWrite ? <Link className="primary-button" to={`/applications/${application.id}/targets/new`}>Add target</Link> : undefined} /> : (
          <div className="data-list">{targetsState.data.slice(0, 5).map((target) => <Link className="data-row" to={`/targets/${target.id}`} key={target.id}><span className="row-icon"><Icon name="target" size={17} /></span><div className="row-primary"><strong>{target.name}</strong><span>{target.base_url}</span></div><span className="environment-label">{target.environment}</span><Icon name="arrow" size={16} /></Link>)}</div>
        )}
      </section>

      <section className="section-block" aria-labelledby="recent-runs-heading">
        <div className="section-heading"><div><p className="eyebrow">Activity</p><h2 id="recent-runs-heading">Recent runs</h2></div><Link className="text-link" to="/runs">View all</Link></div>
        {runsState.status === "loading" ? <LoadingPanel label="Loading runs" /> : runsState.status === "error" ? <ErrorPanel message={runsState.error} /> : runsState.data.length === 0 ? <EmptyState title="No studies for this application" copy="Create a study after an authorized target is ready." /> : (
          <div className="data-list">{runsState.data.slice(0, 5).map((run) => <Link className="data-row" to={`/runs/${run.id}/overview`} key={run.id}><span className="row-icon"><Icon name="runs" size={16} /></span><div className="row-primary"><strong>{studyBrief(run.configuration_snapshot)}</strong><span>{textValue(run.target_snapshot.name, textValue(run.target_snapshot.base_url, "Target"))}</span></div><StatusBadge status={run.status} /><Icon name="arrow" size={16} /></Link>)}</div>
        )}
      </section>

      {canManageLifecycle(workspace.role) ? <LifecyclePanel entityType="application" entityName={application.name} /> : null}
    </>
  );
}

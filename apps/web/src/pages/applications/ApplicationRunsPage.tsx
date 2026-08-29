import { Link, useOutletContext, useParams } from "react-router-dom";

import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { api } from "../../lib/api";
import { studyBrief, textValue } from "../../lib/format";
import { canWriteWorkspace } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function ApplicationRunsPage() {
  const { applicationId = "" } = useParams();
  const { workspace } = useOutletContext<AppShellContext>();
  const appState = useAsync(() => api.getApplication(applicationId), [applicationId]);
  const runsState = useAsync(() => api.listRuns(applicationId), [applicationId]);

  if (appState.status === "loading") return <LoadingPanel label="Loading application" />;
  if (appState.status === "error") return <ErrorPanel message={appState.error} />;

  const canWrite = canWriteWorkspace(workspace.role) && appState.data.status === "active";

  return (
    <>
      <PageHeader eyebrow={appState.data.name} title="Runs" description="Studies created for this application, each with its persisted target and configuration snapshot." action={canWrite ? <Link className="primary-button" to={`/applications/${applicationId}/runs/new`}><Icon name="plus" size={16} /> New study</Link> : undefined} />
      {runsState.status === "loading" ? <LoadingPanel label="Loading runs" /> : runsState.status === "error" ? <ErrorPanel message={runsState.error} /> : runsState.data.length === 0 ? <EmptyState title="No studies yet" copy="Create a study when an authorized target is ready." action={canWrite ? <Link className="primary-button" to={`/applications/${applicationId}/runs/new`}>New study</Link> : undefined} /> : <div className="data-list">{runsState.data.map((run) => <Link className="data-row" to={`/runs/${run.id}/overview`} key={run.id}><span className="row-icon"><Icon name="runs" size={16} /></span><div className="row-primary"><strong>{studyBrief(run.configuration_snapshot)}</strong><span>{textValue(run.target_snapshot.name, textValue(run.target_snapshot.base_url, "Target"))}</span></div><StatusBadge status={run.status} /><Icon name="arrow" size={16} /></Link>)}</div>}
    </>
  );
}

import { useState } from "react";
import { DeleteAction } from "../../components/markettwin/DeleteAction";
import { Link, useOutletContext, useParams } from "react-router-dom";

import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { TestStatusBadge } from "../../components/ui/StatusBadge";
import { api } from "../../lib/api";
import { testBrief, textValue } from "../../lib/format";
import { canManageLifecycle, canWriteWorkspace } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function ApplicationRunsPage() {
  const [revision, setRevision] = useState(0);
  const { applicationId = "" } = useParams();
  const { workspace } = useOutletContext<AppShellContext>();
  const appState = useAsync(() => api.getApplication(applicationId), [applicationId]);
  const runsState = useAsync(() => api.listRuns(applicationId), [applicationId, revision]);

  if (appState.status === "loading") return <LoadingPanel label="Loading application" />;
  if (appState.status === "error") return <ErrorPanel message={appState.error} />;

  const canWrite = canWriteWorkspace(workspace.role) && appState.data.status === "active";

  return (
    <>
      <PageHeader eyebrow={appState.data.name} title="Tests" description="Tests created for this application, each with its persisted target and configuration snapshot." action={canWrite ? <Link className="primary-button" to={`/applications/${applicationId}/runs/new`}><Icon name="plus" size={16} /> New test</Link> : undefined} />
      {runsState.status === "loading" ? <LoadingPanel label="Loading tests" /> : runsState.status === "error" ? <ErrorPanel message={runsState.error} /> : runsState.data.length === 0 ? <EmptyState title="No tests yet" copy="Create a test when an authorized target is ready." action={canWrite ? <Link className="primary-button" to={`/applications/${applicationId}/runs/new`}>New test</Link> : undefined} /> : <div className="data-list">{runsState.data.map((run) => <div className="deletable-row" key={run.id}><Link className="data-row" to={`/runs/${run.id}/overview`}><span className="row-icon"><Icon name="runs" size={16} /></span><div className="row-primary"><strong>{testBrief(run.configuration_snapshot)}</strong><span>{textValue(run.target_snapshot.name, textValue(run.target_snapshot.base_url, "Target"))}</span></div><TestStatusBadge status={run.status} /><Icon name="arrow" size={16} /></Link>{canManageLifecycle(workspace.role) ? <DeleteAction kind="test" id={run.id} name={testBrief(run.configuration_snapshot)} disabled={run.status !== "draft"} onDeleted={() => { setRevision(value => value + 1); }} /> : null}</div>)}</div>}
    </>
  );
}

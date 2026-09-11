import { useState } from "react";
import { DeleteAction } from "../../components/markettwin/DeleteAction";
import { Link, useOutletContext } from "react-router-dom";

import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { api } from "../../lib/api";
import { canManageLifecycle, canWriteWorkspace } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function ApplicationsPage() {
  const [revision, setRevision] = useState(0);
  const { workspace } = useOutletContext<AppShellContext>();
  const state = useAsync(() => api.listApplications(workspace.id), [workspace.id, revision]);
  const canWrite = canWriteWorkspace(workspace.role);

  return (
    <>
      <PageHeader eyebrow="Products" title="Applications" description="Organize the products and environments your team is authorized to evaluate." action={canWrite ? <Link className="primary-button" to="/applications/new"><Icon name="plus" size={16} /> Add application</Link> : undefined} />
      {state.status === "loading" ? <LoadingPanel label="Loading applications" /> : state.status === "error" ? <ErrorPanel message={state.error} /> : state.data.length === 0 ? <EmptyState title="No applications yet" copy="Create an application to organize targets and tests." action={canWrite ? <Link className="primary-button" to="/applications/new">Create application</Link> : undefined} /> : (
        <div className="data-list" role="list">
          {state.data.map((application) => (
            <div className="deletable-row" key={application.id} role="listitem"><Link to={`/applications/${application.id}`} className="data-row">
              <span className="product-icon small">{application.name.slice(0, 2).toUpperCase()}</span>
              <div className="row-primary"><strong>{application.name}</strong><span>{application.description || "No description"}</span></div>
              <StatusBadge status={application.status} />
              <Icon name="arrow" size={16} />
            </Link>{canManageLifecycle(workspace.role) ? <DeleteAction kind="application" id={application.id} name={application.name} onDeleted={() => { setRevision(value => value + 1); }} /> : null}</div>
          ))}
        </div>
      )}
    </>
  );
}

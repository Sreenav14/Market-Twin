import { useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import { DeleteAction } from "../../components/markettwin/DeleteAction";
import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import {
  EmptyState,
  ErrorPanel,
  LoadingPanel,
} from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { ApiError, api } from "../../lib/api";
import { canManageLifecycle, canWriteWorkspace } from "../../lib/permissions";
import { isAuthorizationActive } from "../../lib/targetAuthorization";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function TargetsPage() {
  const [revision, setRevision] = useState(0);
  const { applicationId = "" } = useParams();
  const { workspace } = useOutletContext<AppShellContext>();

  const appState = useAsync(
    () => api.getApplication(applicationId),
    [applicationId],
  );

  const targetsState = useAsync(
    async () => {
      const targets = await api.listTargets(applicationId);
      const targetsWithAuth = await Promise.all(
        targets.map(async (target) => {
          try {
            const authorization = await api.getAuthorization(target.id);
            const active = isAuthorizationActive(authorization);
            return { target, authorization, active };
          } catch (error) {
            if (error instanceof ApiError && error.status === 404) {
              return { target, authorization: null, active: false };
            }
            return { target, authorization: null, active: false };
          }
        }),
      );
      return targetsWithAuth;
    },
    [applicationId, revision],
  );

  if (appState.status === "loading")
    return <LoadingPanel label="Loading application" />;
  if (appState.status === "error")
    return <ErrorPanel message={appState.error} />;

  const canWrite =
    canWriteWorkspace(workspace.role) && appState.data.status === "active";
  const targets = targetsState.data ?? [];

  return (
    <>
      <PageHeader
        eyebrow={appState.data.name}
        title="Targets"
        description="Environments MarketTwin may test after explicit authorization."
        action={
          canWrite ? (
            <Link
              className="primary-button"
              to={`/applications/${applicationId}/targets/new`}
            >
              <Icon name="plus" size={16} /> Add target
            </Link>
          ) : undefined
        }
      />

      <div className="tab-strip" aria-label="Application sections">
        <Link
          className="tab-link"
          to={`/applications/${applicationId}`}
        >
          Overview
        </Link>
        <span className="tab-link active">Targets</span>
        <Link
          className="tab-link"
          to={`/applications/${applicationId}/runs`}
        >
          Tests
        </Link>
      </div>

      {!canWrite ? (
        <div className="panel-note" style={{ marginBottom: "16px" }}>
          Viewing with read-only permissions ({workspace.role}). Workspace Owners or Admins can add or authorize targets.
        </div>
      ) : null}

      {targetsState.status === "loading" ? (
        <LoadingPanel label="Loading targets" />
      ) : targetsState.status === "error" ? (
        <ErrorPanel
          message={targetsState.error}
          action={
            <button
              className="secondary-button"
              type="button"
              onClick={() => setRevision((v) => v + 1)}
            >
              Retry
            </button>
          }
        />
      ) : targets.length === 0 ? (
        <EmptyState
          title="No targets configured"
          copy="Add an environment before creating a test. Initial execution origins are derived from the base URL."
          action={
            canWrite ? (
              <Link
                className="primary-button"
                to={`/applications/${applicationId}/targets/new`}
              >
                <Icon name="plus" size={16} /> Add target
              </Link>
            ) : undefined
          }
        />
      ) : (
        <div className="data-list" role="list">
          {targets.map(({ target, authorization, active }) => {
            const authStatus = active
              ? "authorized"
              : authorization?.status === "revoked"
                ? "revoked"
                : authorization?.status === "authorized"
                  ? "expired"
                  : authorization?.status === "pending"
                    ? "pending"
                    : "not authorized";

            return (
              <div className="deletable-row" key={target.id} role="listitem">
                <Link className="data-row" to={`/targets/${target.id}`}>
                  <span className="row-icon">
                    <Icon name="target" size={17} />
                  </span>
                  <div className="row-primary">
                    <strong>{target.name}</strong>
                    <span style={{ wordBreak: "break-all" }}>{target.base_url}</span>
                  </div>
                  <span className="environment-label">{target.environment}</span>
                  <StatusBadge status={authStatus} />
                  <Icon name="arrow" size={16} />
                </Link>
                {!active && canWrite ? (
                  <Link
                    to={`/targets/${target.id}/authorization`}
                    className="secondary-button compact"
                    style={{ marginRight: "8px", whiteSpace: "nowrap" }}
                  >
                    Authorize
                  </Link>
                ) : null}
                {canManageLifecycle(workspace.role) ? (
                  <DeleteAction
                    kind="target"
                    id={target.id}
                    name={target.name}
                    onDeleted={() => {
                      setRevision((value) => value + 1);
                    }}
                  />
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

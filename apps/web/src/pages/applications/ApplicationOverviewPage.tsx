import { ReactNode, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";
import { LifecyclePanel } from "../../components/ui/LifecyclePanel";
import { PageHeader } from "../../components/ui/PageHeader";
import {
  EmptyState,
  ErrorPanel,
  LoadingPanel,
} from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { ApiError, api } from "../../lib/api";
import { testTitle, textValue } from "../../lib/format";
import { canManageLifecycle, canWriteWorkspace } from "../../lib/permissions";
import { isAuthorizationActive } from "../../lib/targetAuthorization";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function ApplicationOverviewPage() {
  const { applicationId = "" } = useParams();
  const { workspace } = useOutletContext<AppShellContext>();
  const [readinessAttempt, setReadinessAttempt] = useState(0);
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
            return { target, authorization, active, unavailable: false };
          } catch (error) {
            if (error instanceof ApiError && error.status === 404) {
              return { target, authorization: null, active: false, unavailable: false };
            }
            return { target, authorization: null, active: false, unavailable: true };
          }
        }),
      );
      return targetsWithAuth;
    },
    [applicationId, readinessAttempt],
  );
  const runsState = useAsync(
    () => api.listRuns(applicationId),
    [applicationId],
  );
  const canWriteRole = canWriteWorkspace(workspace.role);

  if (appState.status === "loading")
    return <LoadingPanel label="Loading application" />;
  if (appState.status === "error")
    return <ErrorPanel message={appState.error} />;

  const application = appState.data;
  const canWrite = canWriteRole && application.status === "active";

  const targetsData = targetsState.data ?? [];
  const authorizedTargets = targetsData.filter(
    (item) => item.active && item.target.status === "active",
  );
  const firstUnauthorized = targetsData.find(
    (item) => !item.active && !item.unavailable && item.target.status === "active",
  );
  const authorizationUnavailable = targetsData.some((item) => item.unavailable);
  const retryReadiness = (
    <button className="secondary-button compact" onClick={() => setReadinessAttempt((value) => value + 1)}>
      Retry target readiness
    </button>
  );

  let primaryAction: ReactNode = undefined;
  if (canWrite && targetsState.status === "ready") {
    if (targetsData.length === 0) {
      primaryAction = (
        <Link
          className="primary-button"
          to={`/applications/${application.id}/targets/new`}
        >
          <Icon name="plus" size={16} /> Add target
        </Link>
      );
    } else if (authorizedTargets.length === 0 && firstUnauthorized) {
      primaryAction = (
        <Link
          className="primary-button"
          to={`/targets/${firstUnauthorized.target.id}/authorization`}
        >
          <Icon name="shield" size={16} /> Authorize target
        </Link>
      );
    } else if (authorizedTargets.length > 0) {
      primaryAction = (
        <Link
          className="primary-button"
          to={`/applications/${application.id}/runs/new`}
        >
          <Icon name="plus" size={16} /> New test
        </Link>
      );
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Application"
        title={application.name}
        description={
          application.description ||
          "Configure authorized target environments and run browser tests against this application."
        }
        action={primaryAction}
      />
      <div className="tab-strip" aria-label="Application sections">
        <span className="tab-link active">Overview</span>
        <Link
          className="tab-link"
          to={`/applications/${application.id}/targets`}
        >
          Targets{targetsState.status === "ready" ? ` (${targetsData.length})` : ""}
        </Link>
        <Link className="tab-link" to={`/applications/${application.id}/runs`}>
          Tests{runsState.status === "ready" ? ` (${runsState.data.length})` : ""}
        </Link>
      </div>

      <section className="section-block" aria-labelledby="app-targets-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Environments</p>
            <h2 id="app-targets-heading">Targets</h2>
          </div>
          {canWrite && targetsState.status === "ready" ? (
            <Link
              className="secondary-button compact"
              to={`/applications/${application.id}/targets/new`}
            >
              <Icon name="plus" size={14} /> Add target
            </Link>
          ) : null}
        </div>
        {targetsState.status === "loading" ? (
          <LoadingPanel label="Loading targets" />
        ) : targetsState.status === "error" ? (
          <ErrorPanel message={targetsState.error} action={retryReadiness} />
        ) : targetsData.length === 0 ? (
          <EmptyState
            title="No targets configured"
            copy="Add a local, staging, QA, demo, or production environment before running tests."
            action={
              canWrite ? (
                <Link
                  className="primary-button"
                  to={`/applications/${application.id}/targets/new`}
                >
                  <Icon name="plus" size={16} /> Add target
                </Link>
              ) : undefined
            }
          />
        ) : (
          <>
          {authorizationUnavailable ? (
            <ErrorPanel
              message="Authorization status is unavailable for one or more targets. Retry the check to see their testing readiness."
              action={retryReadiness}
            />
          ) : null}
          <div className="data-list" role="list">
            {targetsData.slice(0, 5).map(({ target, authorization, active, unavailable }) => {
              const authStatus = unavailable
                ? "unavailable"
                : active
                ? "authorized"
                : authorization?.status === "revoked"
                  ? "revoked"
                  : authorization?.status === "authorized"
                    ? "expired"
                    : authorization?.status === "pending"
                      ? "pending"
                      : "not authorized";

              return (
                <div key={target.id} role="listitem">
                  <Link
                    className="data-row"
                    to={`/targets/${target.id}`}
                  >
                    <span className="row-icon">
                      <Icon name="target" size={17} />
                    </span>
                    <div className="row-primary">
                      <strong>{target.name}</strong>
                      <span>{target.base_url}</span>
                    </div>
                    <span className="environment-label">{target.environment}</span>
                    <StatusBadge status={authStatus} />
                    <Icon name="arrow" size={16} />
                  </Link>
                </div>
              );
            })}
          </div>
          </>
        )}
      </section>

      <section className="section-block" aria-labelledby="recent-tests-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Activity</p>
            <h2 id="recent-tests-heading">Recent tests</h2>
          </div>
          <Link
            className="text-link"
            to={`/applications/${application.id}/runs`}
          >
            View all
          </Link>
        </div>
        {runsState.status === "loading" ? (
          <LoadingPanel label="Loading tests" />
        ) : runsState.status === "error" ? (
          <ErrorPanel message={runsState.error} />
        ) : (runsState.data?.length ?? 0) === 0 ? (
          <EmptyState
            title="No tests for this application yet"
            copy={
              targetsState.status === "loading"
                ? "Checking target readiness before suggesting a test."
                : targetsState.status === "error" || (authorizationUnavailable && authorizedTargets.length === 0)
                  ? "Target readiness is unavailable. Retry the check in Targets before creating a test."
                  : authorizedTargets.length > 0
                ? "Create a test against your authorized environment."
                : targetsData.length === 0
                  ? "Add a target environment before running tests."
                : "Authorize a target environment before running tests."
            }
            action={
              authorizedTargets.length > 0 && canWrite ? (
                <Link
                  className="primary-button"
                  to={`/applications/${application.id}/runs/new`}
                >
                  <Icon name="plus" size={16} /> New test
                </Link>
              ) : targetsData.length > 0 && firstUnauthorized && canWrite ? (
                <Link
                  className="secondary-button"
                  to={`/targets/${firstUnauthorized.target.id}/authorization`}
                >
                  <Icon name="shield" size={16} /> Authorize target
                </Link>
              ) : undefined
            }
          />
        ) : (
          <div className="data-list" role="list">
            {runsState.data.slice(0, 5).map((run) => (
              <div key={run.id} role="listitem">
                <Link
                  className="data-row"
                  to={`/runs/${run.id}/overview`}
                >
                  <span className="row-icon">
                    <Icon name="runs" size={16} />
                  </span>
                  <div className="row-primary">
                    <strong>{testTitle(run)}</strong>
                    <span>
                      {textValue(
                        run.target_snapshot.name,
                        textValue(run.target_snapshot.base_url, "Target"),
                      )}
                    </span>
                  </div>
                  <StatusBadge status={run.status} />
                  <Icon name="arrow" size={16} />
                </Link>
              </div>
            ))}
          </div>
        )}
      </section>

      {canManageLifecycle(workspace.role) ? (
        <LifecyclePanel
          entityType="application"
          entityName={application.name}
          entityId={application.id}
          returnTo="/applications"
        />
      ) : null}
    </>
  );
}

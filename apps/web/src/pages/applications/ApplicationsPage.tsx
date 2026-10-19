import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { DeleteAction } from "../../components/markettwin/DeleteAction";
import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import {
  EmptyState,
  ErrorPanel,
  LoadingPanel,
} from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { api } from "../../lib/api";
import { canManageLifecycle, canWriteWorkspace } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function ApplicationsPage() {
  const [revision, setRevision] = useState(0);
  const [search, setSearch] = useState("");
  const { workspace } = useOutletContext<AppShellContext>();
  const state = useAsync(
    async () => {
      const apps = await api.listApplications(workspace.id);
      const targetCounts = await Promise.all(
        apps.map(async (app) => {
          try {
            const targets = await api.listTargets(app.id);
            return { id: app.id, count: targets.length };
          } catch {
            return { id: app.id, count: null };
          }
        }),
      );
      const targetCountMap = Object.fromEntries(
        targetCounts.map((tc) => [tc.id, tc.count]),
      );
      return { applications: apps, targetCountMap };
    },
    [workspace.id, revision],
  );
  const canWrite = canWriteWorkspace(workspace.role);

  const applications = state.data?.applications ?? [];
  const targetCountMap = state.data?.targetCountMap ?? {};

  const filteredApps = applications.filter((app) => {
    if (!search.trim()) return true;
    const term = search.toLowerCase();
    return (
      app.name.toLowerCase().includes(term) ||
      (app.description && app.description.toLowerCase().includes(term))
    );
  });

  return (
    <>
      <PageHeader
        title="Applications"
        description="Manage your applications and their testing environments."
        action={
          canWrite ? (
            <Link className="primary-button" to="/applications/new">
              <Icon name="plus" size={16} /> Add application
            </Link>
          ) : undefined
        }
      />

      {!canWrite ? (
        <div className="panel-note" style={{ marginBottom: "16px" }}>
          Viewing with read-only permissions ({workspace.role}). Contact a workspace owner or admin to add applications.
        </div>
      ) : null}

      {state.status === "loading" ? (
        <LoadingPanel label="Loading applications" />
      ) : state.status === "error" ? (
        <ErrorPanel
          message={state.error}
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
      ) : applications.length === 0 ? (
        <EmptyState
          title="No applications yet"
          copy={
            canWrite
              ? "Create an application to organize target environments and run evidence-based browser tests."
              : "No applications have been created in this workspace yet."
          }
          action={
            canWrite ? (
              <Link className="primary-button" to="/applications/new">
                <Icon name="plus" size={16} /> Create application
              </Link>
            ) : undefined
          }
        />
      ) : (
        <>
          {applications.length > 2 ? (
            <div className="filter-bar" style={{ marginBottom: "16px" }}>
              <div className="search-field">
                <input
                  type="search"
                  placeholder="Filter applications by name or description…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  aria-label="Filter applications"
                />
              </div>
              {search ? (
                <button
                  className="secondary-button compact"
                  type="button"
                  onClick={() => setSearch("")}
                >
                  Clear filter
                </button>
              ) : null}
            </div>
          ) : null}

          {filteredApps.length === 0 ? (
            <div className="panel" style={{ textAlign: "center", padding: "32px 16px" }}>
              <p style={{ color: "var(--text-2)", margin: "0 0 12px" }}>
                No applications match &ldquo;{search}&rdquo;.
              </p>
              <button
                className="secondary-button compact"
                type="button"
                onClick={() => setSearch("")}
              >
                Clear filter
              </button>
            </div>
          ) : (
            <div className="data-list" role="list">
              {filteredApps.map((application) => {
                const targetCount = targetCountMap[application.id];
                return (
                  <div
                    className="deletable-row"
                    key={application.id}
                    role="listitem"
                  >
                    <Link
                      to={`/applications/${application.id}`}
                      className="data-row"
                    >
                      <span className="product-icon small">
                        {application.name.slice(0, 2).toUpperCase()}
                      </span>
                      <div className="row-primary">
                        <strong>{application.name}</strong>
                        <span>{application.description || "No description"}</span>
                      </div>
                      {targetCount !== null && targetCount !== undefined ? (
                        <span className="environment-label">
                          {targetCount === 1 ? "1 target" : `${targetCount} targets`}
                        </span>
                      ) : null}
                      <StatusBadge status={application.status} />
                      <Icon name="arrow" size={16} />
                    </Link>
                    {canManageLifecycle(workspace.role) ? (
                      <DeleteAction
                        kind="application"
                        id={application.id}
                        name={application.name}
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
      )}
    </>
  );
}

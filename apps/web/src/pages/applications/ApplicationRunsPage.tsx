import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { DeleteAction } from "../../components/markettwin/DeleteAction";
import { Link, useOutletContext, useParams, useSearchParams } from "react-router-dom";

import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import {
  EmptyState,
  ErrorPanel,
  LoadingPanel,
} from "../../components/ui/StateViews";
import { TestStatusBadge } from "../../components/ui/StatusBadge";
import { api } from "../../lib/api";
import { testTitle, textValue } from "../../lib/format";
import { canDeleteTest, terminalTestStatuses } from "../../lib/results";
import { canManageLifecycle, canWriteWorkspace } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function ApplicationRunsPage() {
  const [revision, setRevision] = useState(0);
  const { applicationId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const search = params.get("q") ?? "";
  const status = params.get("status") ?? "all";
  const sort = params.get("sort") === "oldest" ? "oldest" : "recent";
  const { workspace, user } = useOutletContext<AppShellContext>();
  const appState = useAsync(
    () => api.getApplication(applicationId),
    [applicationId, revision],
  );
  const runsState = useQuery({
    queryKey: ["application-tests", user.id, workspace.id, applicationId],
    queryFn: () => api.listRuns(applicationId),
    refetchInterval: (query) => query.state.data?.some((run) =>
      run.status !== "draft" && !terminalTestStatuses.has(run.status),
    ) ? 5000 : false,
  });

  if (appState.status === "loading")
    return <LoadingPanel label="Loading application" />;
  if (appState.status === "error")
    return <ErrorPanel message={appState.error} action={<button className="secondary-button"
      onClick={() => setRevision((value) => value + 1)}>Try again</button>} />;

  const canWrite =
    canWriteWorkspace(workspace.role) && appState.data.status === "active";
  const runs = runsState.data ?? [];
  const filteredRuns = runs.filter((run) =>
    (status === "all" || (status === "in_progress"
      ? ["planning", "queued", "running"].includes(run.status)
      : status === "stopped" ? ["failed", "cancelled", "timed_out", "policy_blocked"].includes(run.status)
      : run.status === status))
    && `${testTitle(run)} ${textValue(run.target_snapshot.name, "")}`.toLowerCase().includes(search.trim().toLowerCase()),
  ).sort((a, b) => {
    const aCreated = Date.parse(a.created_at ?? "");
    const bCreated = Date.parse(b.created_at ?? "");
    if (Number.isFinite(aCreated) !== Number.isFinite(bCreated))
      return Number.isFinite(aCreated) ? -1 : 1;
    const chronological = Number.isFinite(aCreated) && Number.isFinite(bCreated)
      ? aCreated - bCreated : 0;
    const order = chronological || (a.test_number ?? 0) - (b.test_number ?? 0);
    return sort === "oldest" ? order : -order;
  });
  function filter(key: string, value: string) {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      if (!value || value === "all") next.delete(key);
      else next.set(key, value);
      return next;
    }, { replace: true });
  }

  return (
    <>
      <Link className="back-link" to="/runs">All tests</Link>
      <PageHeader
        eyebrow={appState.data.name}
        title="Tests"
        description={`Browse tests for ${appState.data.name}.`}
        action={
          canWrite ? (
            <Link
              className="primary-button"
              to={`/applications/${applicationId}/runs/new`}
            >
              <Icon name="plus" size={16} /> Start a test
            </Link>
          ) : undefined
        }
      />
      {runsState.isPending ? (
        <LoadingPanel label="Loading tests" />
      ) : !runsState.data ? (
        <ErrorPanel message={runsState.error?.message || "Could not load tests."} action={<button className="secondary-button"
          onClick={() => void runsState.refetch()}>Try again</button>} />
      ) : runsState.data.length === 0 ? (
        <EmptyState
          title="No tests yet"
          copy="Create a test when an authorized target is ready."
          action={
            canWrite ? (
              <Link
                className="primary-button"
                to={`/applications/${applicationId}/runs/new`}
              >
                Start a test
              </Link>
            ) : undefined
          }
        />
      ) : (
        <>
        {runsState.isError ? <p role="alert" className="inline-note">Could not refresh tests. Showing the last loaded data. <button className="text-link" onClick={() => void runsState.refetch()}>Try again</button></p> : null}
        <div className="filter-bar">
          <div className="search-field"><input type="search" aria-label="Find a test"
            placeholder="Find a test…" value={search} onChange={(event) => filter("q", event.target.value)} /></div>
          <select className="text-input filter-control" aria-label="Filter tests by status" value={status} onChange={(event) => filter("status", event.target.value)}>
            <option value="all">All statuses</option><option value="awaiting_human">Needs your help</option>
            <option value="in_progress">In progress</option><option value="completed">Completed</option>
            <option value="stopped">Failed / stopped</option><option value="draft">Drafts</option>
          </select>
          <select className="text-input filter-control" aria-label="Sort tests" value={sort} onChange={(event) => filter("sort", event.target.value)}>
            <option value="recent">Recent first</option><option value="oldest">Oldest first</option>
          </select>
          {search || status !== "all" || sort !== "recent" ? <button className="secondary-button compact"
            onClick={() => setParams({}, { replace: true })}>Clear filters</button> : null}
        </div>
        {filteredRuns.length === 0 ? <EmptyState title="No matching tests" copy="Try another search or status."
          action={<button className="secondary-button" onClick={() => setParams({}, { replace: true })}>Clear filters</button>} /> :
        <div className="data-list">
          {filteredRuns.map((run) => (
            <div className="deletable-row" key={run.id}>
              <Link className="data-row" to={`/runs/${run.id}/${run.status === "awaiting_human" ? "human-action" : ["running", "planning", "queued"].includes(run.status) ? "watch" : run.status === "draft" ? "overview" : "results"}`}>
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
                  {run.status_reason ? <span>{run.status_reason}</span> : null}
                </div>
                <TestStatusBadge status={run.status} />
                <Icon name="arrow" size={16} />
              </Link>
              {canManageLifecycle(workspace.role) ? (
                <DeleteAction
                  kind="test"
                  id={run.id}
                  name={testTitle(run)}
                  disabled={!canDeleteTest(run.status)}
                  onDeleted={() => {
                    void runsState.refetch();
                  }}
                />
              ) : null}
            </div>
          ))}
        </div>}
        </>
      )}
    </>
  );
}

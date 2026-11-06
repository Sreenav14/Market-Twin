import { useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { TestStatusBadge } from "../../components/ui/StatusBadge";
import { api, type TestRun } from "../../lib/api";
import { testTitle } from "../../lib/format";
import { canWriteWorkspace } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import { useWorkspaceTests } from "../../lib/useWorkspaceTests";
import { testDestination } from "../concept/WorkspaceDashboardPage";
import type { AppShellContext } from "../../layouts/AppShell";

// Workspace-wide status filters, restored for the URLs the pre-concept page
// supported (e.g. /runs?status=awaiting_human). An unknown value falls back
// to the application picker instead of being silently honoured or dropped.
const STATUS_FILTERS: Record<string, { label: string; matches: (test: TestRun) => boolean }> = {
  awaiting_human: { label: "Tests that need your help", matches: (test) => test.status === "awaiting_human" },
  in_progress: { label: "Tests in progress", matches: (test) => ["planning", "queued", "running"].includes(test.status) },
  completed: { label: "Completed tests", matches: (test) => test.status === "completed" },
  stopped: { label: "Stopped tests", matches: (test) => ["failed", "cancelled"].includes(test.status) },
  draft: { label: "Draft tests", matches: (test) => test.status === "draft" },
};

function StatusRunsView({ filterKey }: { filterKey: string }) {
  const { user, workspace } = useOutletContext<AppShellContext>();
  const [, setParams] = useSearchParams();
  const state = useWorkspaceTests(user.id, workspace.id);
  const filter = STATUS_FILTERS[filterKey];
  const clearFilter = () => setParams({}, { replace: true });
  if (state.isPending) return <LoadingPanel label="Loading tests" />;
  if (!state.data) return <ErrorPanel message={state.error?.message || "Could not load tests."}
    action={<button className="secondary-button" onClick={() => void state.refetch()}>Try again</button>} />;
  const appNames = new Map(state.data.applications.map((app) => [app.id, app.name]));
  const runs = state.data.runs.filter(filter.matches)
    .sort((a, b) => (Date.parse(b.created_at ?? "") || 0) - (Date.parse(a.created_at ?? "") || 0));
  return (
    <>
      <PageHeader title="Tests" description={filter.label}
        action={<button className="secondary-button" onClick={clearFilter}>Clear filter</button>} />
      {runs.length ? <div className="data-list" role="list" aria-label={filter.label}>
        {runs.map((test) => {
          const action = testDestination(test);
          return <div role="listitem" key={test.id}>
            <Link className="data-row" to={action.to}>
              <span className="product-icon small" aria-hidden="true">{(appNames.get(test.application_id) ?? "?").slice(0, 2).toUpperCase()}</span>
              <div className="row-primary"><strong>{testTitle(test)}</strong><span>{appNames.get(test.application_id) ?? "Application"}</span></div>
              <TestStatusBadge status={test.status} />
              <span className="text-link">{action.label}</span><Icon name="arrow" size={16} />
            </Link>
          </div>;
        })}
      </div> : <EmptyState title="No tests match this filter" copy="Clear the filter to browse tests by application."
        action={<button className="secondary-button" onClick={clearFilter}>Clear filter</button>} />}
    </>
  );
}

function ApplicationPicker() {
  const { workspace } = useOutletContext<AppShellContext>();
  const [params, setParams] = useSearchParams();
  const [revision, setRevision] = useState(0);
  const search = params.get("q") ?? "";
  const state = useAsync(() => api.listApplications(workspace.id), [workspace.id, revision]);
  const applications = state.data ?? [];
  const filtered = applications.filter((app) =>
    `${app.name} ${app.description ?? ""}`.toLowerCase().includes(search.trim().toLowerCase()),
  );

  function setSearch(value: string) {
    setParams(value ? { q: value } : {}, { replace: true });
  }

  return (
    <>
      <PageHeader title="Tests" description="Choose an application to see its tests."
        action={canWriteWorkspace(workspace.role)
          ? <Link className="primary-button" to="/applications/new">Add application</Link> : undefined} />
      {state.status === "loading" ? <LoadingPanel label="Loading applications" />
        : state.status === "error" ? <ErrorPanel message={state.error}
          action={<button className="secondary-button" onClick={() => setRevision((value) => value + 1)}>Try again</button>} />
        : applications.length === 0 ? <EmptyState title="No applications yet"
          copy="Add an application, then create tests for its authorized targets."
          action={canWriteWorkspace(workspace.role)
            ? <Link className="primary-button" to="/applications/new">Add application</Link> : undefined} />
        : <>
          <div className="filter-bar">
            <div className="search-field">
              <input type="search" aria-label="Find an application" placeholder="Find an application…"
                value={search} onChange={(event) => setSearch(event.target.value)} />
            </div>
            {search ? <button className="secondary-button compact" onClick={() => setSearch("")}>Clear search</button> : null}
          </div>
          {filtered.length ? <div className="data-list" role="list" aria-label="Applications with tests">
            {filtered.map((app) => <div role="listitem" key={app.id}>
              <Link className="data-row" to={`/applications/${app.id}/runs`}>
                <span className="product-icon small" aria-hidden="true">{app.name.slice(0, 2).toUpperCase()}</span>
                <div className="row-primary"><strong>{app.name}</strong><span>{app.description || "View tests for this application"}</span></div>
                <span className="text-link">View tests</span><Icon name="arrow" size={16} />
              </Link>
            </div>)}
          </div> : <EmptyState title="No matching applications" copy="Try another application name."
            action={<button className="secondary-button" onClick={() => setSearch("")}>Clear search</button>} />}
        </>}
    </>
  );
}

export function RunsPage() {
  const [params] = useSearchParams();
  const status = params.get("status") ?? "";
  if (status && STATUS_FILTERS[status]) return <StatusRunsView filterKey={status} />;
  return <ApplicationPicker />;
}

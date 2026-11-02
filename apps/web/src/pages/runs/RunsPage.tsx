import { useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { api } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import type { AppShellContext } from "../../layouts/AppShell";

export function RunsPage() {
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

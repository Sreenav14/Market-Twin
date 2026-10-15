import { DeleteAction } from "../../components/markettwin/DeleteAction";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { Search, ArrowUpRight } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import {
  EmptyState,
  ErrorPanel,
  LoadingPanel,
} from "../../components/ui/StateViews";
import { TestStatusBadge } from "../../components/ui/StatusBadge";
import { Button } from "../../components/ui/button";
import { testTitle, testBrief, textValue } from "../../lib/format";
import { canDeleteTest } from "../../lib/results";
import { useWorkspaceTests } from "../../lib/useWorkspaceTests";
import { canManageLifecycle, canWriteWorkspace } from "../../lib/permissions";
import { AppShellContext } from "../../layouts/AppShell";

export function RunsPage() {
  const { workspace, user } = useOutletContext<AppShellContext>();
  const state = useWorkspaceTests(user.id, workspace.id);
  const [params, setParams] = useSearchParams();
  const search = params.get("q") || "";
  const status = params.get("status") || "all";
  const runs = (state.data?.runs || []).filter(
    (run) =>
      (status === "all" || run.status === status) &&
      `${testTitle(run)} ${testBrief(run.configuration_snapshot)}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  function filter(key: string, value: string) {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (!value || value === "all") next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true },
    );
  }
  return (
    <>
      <PageHeader
        title="Tests"
        description="Track execution and review results."
        action={
          canWriteWorkspace(workspace.role) ? (
            <Link className="primary-button" to="/applications">
              New test
            </Link>
          ) : undefined
        }
      />
      {state.isPending ? (
        <LoadingPanel label="Loading tests" />
      ) : !state.data ? (
        <ErrorPanel
          message={state.error?.message || "Could not load tests."}
          action={
            <Button variant="secondary" onClick={() => void state.refetch()}>
              Try again
            </Button>
          }
        />
      ) : (
        <>
          {state.isError ? (
            <p className="inline-note" role="alert">
              Could not refresh tests. Showing the last loaded data.{" "}
              <Button variant="ghost" size="sm" onClick={() => void state.refetch()}>
                Try again
              </Button>
            </p>
          ) : null}
          <div className="filter-bar">
            <div className="search-field">
              <Search size={17} aria-hidden="true" />
              <input
                aria-label="Search tests"
                value={search}
                onChange={(event) => filter("q", event.target.value)}
                placeholder="Find a test…"
              />
            </div>
            <select
              className="text-input filter-control"
              aria-label="Test status"
              value={status}
              onChange={(event) => filter("status", event.target.value)}
            >
              <option value="all">All statuses</option>
              {[...new Set(state.data.runs.map((run) => run.status))]
                .sort()
                .map((value) => (
                  <option key={value} value={value}>
                    {value.replaceAll("_", " ")}
                  </option>
                ))}
            </select>
          </div>
          {runs.length ? (
            <div className="study-table">
              <div className="study-table-heading">
                <span>Test / target</span>
                <span>Status</span>
              </div>
              {runs.map((run) => (
                <div className="deletable-row" key={run.id}>
                  <Link
                    className={`study-row ${run.status === "awaiting_human" ? "awaiting-human-row" : ""}`}
                    to={`/runs/${run.id}/${run.status === "awaiting_human" ? "human-action" : "overview"}`}
                    aria-label={run.status === "awaiting_human" ? `Open Human Assistance for ${testTitle(run)}` : `Open ${testTitle(run)}`}
                  >
                    <span className="study-row-copy">
                      <strong>{testTitle(run)}</strong>
                      <span>
                        {textValue(run.target_snapshot.name, "Target")}
                        {` · ${textValue(run.target_snapshot.environment, "Environment")} · ${run.configuration_snapshot.execution_mode === "deep_feature_v1" ? "Feature cases" : "Persona journeys"}`}
                        <span className="monospace">{run.id.slice(0, 8)}</span>
                      </span>
                    </span>
                    <TestStatusBadge status={run.status} />
                    <ArrowUpRight size={18} aria-hidden="true" />
                  </Link>
                  {canManageLifecycle(workspace.role) ? (
                    <DeleteAction
                      kind="test"
                      id={run.id}
                      name={testTitle(run)}
                      disabled={!canDeleteTest(run.status)}
                      onDeleted={() => {
                        void state.refetch();
                      }}
                    />
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title={
                state.data.runs.length
                  ? "No matching tests"
                  : "No tests yet"
              }
              copy={
                state.data.runs.length
                  ? "Try another search or clear your filters."
                  : "Choose an application to create your first test."
              }
              action={
                state.data.runs.length ? (
                  <Button variant="secondary" onClick={() => setParams({})}>
                    Clear filters
                  </Button>
                ) : (
                  <Link className="primary-button" to="/applications">
                    Choose application
                  </Link>
                )
              }
            />
          )}
        </>
      )}
    </>
  );
}

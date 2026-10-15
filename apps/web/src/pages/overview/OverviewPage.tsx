import { Link, useOutletContext } from "react-router-dom";
import { ArrowUpRight, Plus, FlaskConical } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import {
  EmptyState,
  ErrorPanel,
  LoadingPanel,
} from "../../components/ui/StateViews";
import { TestStatusBadge } from "../../components/ui/StatusBadge";
import { Button } from "../../components/ui/button";
import { canWriteWorkspace } from "../../lib/permissions";
import { useWorkspaceTests } from "../../lib/useWorkspaceTests";
import { testTitle, textValue } from "../../lib/format";
import { AppShellContext } from "../../layouts/AppShell";

export function OverviewPage() {
  const { workspace, user } = useOutletContext<AppShellContext>();
  const state = useWorkspaceTests(user.id, workspace.id);
  const canWrite = canWriteWorkspace(workspace.role);
  if (state.isPending) return <LoadingPanel label="Loading workspace" />;
  if (!state.data)
    return (
      <ErrorPanel
        message={state.error?.message || "Could not load the workspace."}
        action={
          <Button variant="secondary" onClick={() => void state.refetch()}>
            Try again
          </Button>
        }
      />
    );
  const { applications, runs } = state.data;
  const completed = runs.filter((run) => run.status === "completed");
  const awaitingHuman = runs.filter((run) => run.status === "awaiting_human");
  const active = runs.filter((run) =>
    ["planning", "queued", "running"].includes(run.status),
  );
  return (
    <>
      <PageHeader
        title="Workspace overview"
        description="Test activity and applications in your workspace."
        action={
          canWrite && applications.length > 0 ? (
            <Link
              className="primary-button"
              to={
                applications.length === 1
                  ? `/applications/${applications[0].id}/runs/new`
                  : applications.length
                    ? "/applications"
                    : "/applications/new"
              }
            >
              <Plus size={17} aria-hidden="true" />
              New test
            </Link>
          ) : undefined
        }
      />
      {state.isError ? (
        <p className="inline-note" role="alert">
          Could not refresh tests. Showing the last loaded data.{" "}
          <Button variant="ghost" size="sm" onClick={() => void state.refetch()}>
            Try again
          </Button>
        </p>
      ) : null}
      {applications.length === 0 ? (
        <EmptyState
          title="Add your first application"
          copy="Connect a target environment to start testing."
          action={
            canWrite ? (
              <Link className="primary-button" to="/applications/new">
                Add application
              </Link>
            ) : undefined
          }
        />
      ) : (
        <>
          {awaitingHuman.length > 0 ? (
            <section className="mt-overview-attention" aria-labelledby="awaiting-human-heading">
              <div className="section-heading">
                <h2 id="awaiting-human-heading">Awaiting your attention</h2>
                <span>{awaitingHuman.length} {awaitingHuman.length === 1 ? "test" : "tests"}</span>
              </div>
              <div className="mt-attention-row-list">
                {awaitingHuman.map((run) => (
                  <Link className="mt-attention-row" to={`/runs/${run.id}/human-action`} key={run.id}>
                    <span><strong>{testTitle(run)}</strong><small>{textValue(run.target_snapshot.name, "Target")}</small></span>
                    <span>Continue test</span>
                    <ArrowUpRight size={18} aria-hidden="true" />
                  </Link>
                ))}
              </div>
            </section>
          ) : null}
          <dl className="workspace-metrics">
            <div>
              <dt>Applications</dt>
              <dd>{applications.length}</dd>
            </div>
            <div>
              <dt>Tests created</dt>
              <dd>{runs.length}</dd>
            </div>
            <div>
              <dt>In progress</dt>
              <dd>
                {active.length}
                {active.length > 0 ? <span className="metric-signal" aria-hidden="true" /> : null}
              </dd>
            </div>
            <div>
              <dt>Execution completed</dt>
              <dd>{completed.length}</dd>
            </div>
          </dl>
          <div className="overview-layout">
            <section>
              <div className="section-heading">
                <h2>Test activity</h2>
                <Link className="text-link" to="/runs">
                  All tests
                </Link>
              </div>
              {runs.length === 0 ? (
                <div className="first-study">
                  <FlaskConical size={30} aria-hidden="true" />
                  <h3>No tests yet</h3>
                  <p>
                    Create a test for a user task you want to evaluate.
                  </p>
                  <Link
                    className="secondary-button"
                    to={
                      applications.length === 1
                        ? `/applications/${applications[0].id}/runs/new`
                        : "/applications"
                    }
                  >
                    Create your first test
                  </Link>
                </div>
              ) : (
                <div className="study-table">
                  {runs.slice(0, 6).map((run) => (
                    <Link
                      className="study-row"
                      to={`/runs/${run.id}/overview`}
                      key={run.id}
                    >
                      <span className="study-row-copy">
                        <strong>{testTitle(run)}</strong>
                        <span>
                          {textValue(run.target_snapshot.name, "Target")}
                        </span>
                      </span>
                      <TestStatusBadge status={run.status} />
                      <ArrowUpRight size={18} aria-hidden="true" />
                    </Link>
                  ))}
                </div>
              )}
            </section>
            <aside className="application-index">
              <div className="section-heading">
                <h2>Applications</h2>
                <Link className="text-link" to="/applications">
                  View all
                </Link>
              </div>
              {applications.slice(0, 6).map((application) => (
                <Link
                  to={`/applications/${application.id}`}
                  className="application-index-row"
                  key={application.id}
                >
                  <span className="product-icon small">
                    {application.name.slice(0, 2).toUpperCase()}
                  </span>
                  <span>
                    <strong>{application.name}</strong>
                    <small>{application.status}</small>
                  </span>
                  <ArrowUpRight size={16} aria-hidden="true" />
                </Link>
              ))}
            </aside>
          </div>
        </>
      )}
      <section className="overview-knowledge-tools" aria-label="Prepare knowledge for testing">
        <div><h2>Knowledge for tests <span className="muted">Optional</span></h2><p className="muted">Ingest a source, review and approve its knowledge, then attach it to an application before selecting it for a test.</p></div>
        <div className="inline-actions"><Link className="text-link" to="/ingestion">Ingest knowledge</Link><Link className="text-link" to="/knowledge/review">Review knowledge</Link></div>
      </section>
      <details className="mt-progressive-help">
        <summary>How tests work</summary>
        <p>Planning creates simulated perspectives and missions. Execution records browser journeys; deterministic feature cases may also run alongside persona journeys. Evaluation follows execution and reviews saved reports and evidence.</p>
        <p>Creating a test saves a draft. Select Start when you are ready. Journey results, feature cases, and evaluation are separate views.</p>
      </details>
    </>
  );
}

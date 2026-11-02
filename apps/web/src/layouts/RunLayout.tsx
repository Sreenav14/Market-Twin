import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Link,
  NavLink,
  Outlet,
  useOutletContext,
  useParams,
  useNavigate,
  useLocation,
} from "react-router-dom";
import { ArrowLeft, Play, RefreshCw } from "lucide-react";
import { PageHeader } from "../components/ui/PageHeader";
import {
  ErrorPanel,
  LoadingPanel,
  Spinner,
} from "../components/ui/StateViews";
import { StatusBadge, TestStatusBadge } from "../components/ui/StatusBadge";
import { DeleteAction } from "../components/markettwin/DeleteAction";
import { KafkaStatusBadge } from "../components/markettwin/KafkaStatusBadge";
import { canManageLifecycle } from "../lib/permissions";
import { Button } from "../components/ui/button";
import { ApiError, TestRun, RunResults, api } from "../lib/api";
import { testTitle, testReference, textValue } from "../lib/format";
import { canDeleteTest, terminalTestStatuses } from "../lib/results";
import { AppShellContext } from "./AppShell";
import { RunFlowPanel } from "../components/markettwin/RunFlowPanel";
import { RunPreflightPanel } from "../components/markettwin/RunPreflightPanel";
import { HumanAssistanceHost } from "../pages/runs/HumanActionPage";

export type ResultsState =
  | { status: "loading" | "waiting"; data: null; error: null }
  | { status: "ready"; data: RunResults; error: null }
  | { status: "error"; data: null; error: string };

export interface RunContext extends AppShellContext {
  run: TestRun;
  results: ResultsState;
  refresh: () => void;
}

export function RunLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const appContext = useOutletContext<AppShellContext>();
  const { runId = "" } = useParams();
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const runQuery = useQuery({
    queryKey: ["run", appContext.user.id, runId],
    queryFn: ({ signal }) => api.getRun(runId, signal),
    refetchInterval: (query) =>
      query.state.data && !terminalTestStatuses.has(query.state.data.status)
        ? 5_000
        : false,
  });
  const preflight = useQuery({ queryKey: ["run-preflight", appContext.user.id, runId],
    queryFn: () => api.getRunPreflight(runId), enabled: runQuery.data?.status === "draft", retry: false });
  async function startRun() {
    if (starting || runQuery.data?.status !== "draft") return;

    setStarting(true);
    setStartError(null);

    try {
      await api.startRun(runId);
      await runQuery.refetch();
      navigate(`/runs/${runId}/watch`);
    } catch (error) {
      setStartError(
        error instanceof Error
          ? error.message
          : "Could not start the test. Please try again.",
      );
    } finally {
      setStarting(false);
    }
  }
  const resultsQuery = useQuery({
    queryKey: ["results", appContext.user.id, runId],
    enabled: runQuery.data?.status === "completed",
    queryFn: async ({ signal }) => {
      try {
        return await api.getRunResults(runId, signal);
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) return null;
        throw error;
      }
    },
    refetchInterval: (query) =>
      query.state.status !== "error" && query.state.data === null
        ? 5_000
        : false,
  });
  const refresh = () => {
    void runQuery.refetch();
    if (runQuery.data?.status === "completed") void resultsQuery.refetch();
  };
  if (runQuery.isPending) return <LoadingPanel label="Loading test" />;
  if (runQuery.isError)
    return (
      <ErrorPanel
        message={runQuery.error.message}
        action={
          <Button variant="secondary" onClick={refresh}>
            Try again
          </Button>
        }
      />
    );
  const run = runQuery.data;
  const executionMode = run.configuration_snapshot.execution_mode === "discovery_contract_v1"
    ? "Explore, approve and test"
    : run.configuration_snapshot.execution_mode === "deep_feature_v1"
    ? "Feature cases · deterministic execution"
    : "Persona journeys";
  const results: ResultsState =
    run.status !== "completed"
      ? { status: "waiting", data: null, error: null }
      : resultsQuery.isError
        ? { status: "error", data: null, error: resultsQuery.error.message }
        : resultsQuery.data === null
          ? { status: "waiting", data: null, error: null }
          : resultsQuery.data
            ? { status: "ready", data: resultsQuery.data, error: null }
            : { status: "loading", data: null, error: null };

  return (
    <>
      <div className="study-utility">
        <Link className="back-link" to={`/applications/${run.application_id}/runs`}>
          <ArrowLeft size={15} aria-hidden="true" />
          Application tests
        </Link>
        <span className="monospace">{testReference(run)}</span>
      </div>
      <PageHeader
        eyebrow="Test"
        title={testTitle(run)}
        description={`${textValue(run.target_snapshot.name, "Target")} · ${textValue(run.target_snapshot.environment, "Environment")} · ${executionMode}`}
        action={
          <div className="header-actions">
            {run.configuration_snapshot.execution_mode === "discovery_contract_v1" ? <StatusBadge status={results.status === "ready" ? "Completed" : ({ discovering: "Exploring", awaiting_approval: "Awaiting test approval", executing: "Testing", evaluating: "Writing report" } as Record<string, string>)[String(run.configuration_snapshot.discovery_stage)] || run.status} /> : <TestStatusBadge status={run.status} />}
            {canManageLifecycle(appContext.workspace.role) &&
            run.status === "draft" ? (
              <>
                <KafkaStatusBadge />
                <Button
                  className="start-test-button"
                  onClick={() => void startRun()}
                  disabled={starting || !preflight.data?.ready}
                >
                  {starting ? (
                    <>
                      <Spinner />
                      Starting…
                    </>
                  ) : (
                    <>
                      <Play size={16} aria-hidden="true" />
                      Start test
                    </>
                  )}
                </Button>
              </>
            ) : null}
            {canManageLifecycle(appContext.workspace.role) ? (
              <DeleteAction
                kind="test"
                id={run.id}
                name={testTitle(run)}
                disabled={!canDeleteTest(run.status)}
                onDeleted={() => navigate(`/applications/${run.application_id}/runs`)}
              />
            ) : null}
            <Button
              variant="ghost"
              size="icon"
              aria-label="Refresh test"
              onClick={refresh}
              disabled={runQuery.isFetching || resultsQuery.isFetching}
            >
              <RefreshCw size={17} aria-hidden="true" />
            </Button>
          </div>
        }
      />
      {startError ? (
        <p className="composer-error" role="alert">
          {startError}
        </p>
      ) : null}
      {run.status === "draft" ? <RunPreflightPanel data={preflight.data} error={preflight.error?.message} loading={preflight.isFetching} onRefresh={() => void preflight.refetch()} /> : null}
      {run.configuration_snapshot.discovery_stage === "awaiting_approval" && !location.pathname.endsWith("/contract") ? <section className="panel"><h2>Approve the tests</h2><p>Exploration is complete. Review the journeys and checks before testing begins.</p><Link to={`/runs/${run.id}/contract`}>Review the tests</Link></section> : null}
      {run.status === "awaiting_human" && run.configuration_snapshot.discovery_stage !== "awaiting_approval" && !location.pathname.endsWith("/human-action") && !location.pathname.endsWith("/activity") && !location.pathname.endsWith("/watch") ? (
        <section className="run-action-required" aria-labelledby="run-action-required-title">
          <div>
            <p className="section-label">Action required</p>
            <h2 id="run-action-required-title">A human action is holding this test</h2>
            <p>The agent is paused until an authorized operator completes or skips the affected work.</p>
          </div>
          <Link className="primary-button" aria-label="Open Human Assistance for this test" to={`/runs/${run.id}/watch`}>Watch live</Link>
        </section>
      ) : null}
      <div className="run-workspace">
      <div className="run-workspace-content">
      <nav className="tab-strip" aria-label="Test sections">
        {run.configuration_snapshot.execution_mode === "discovery_contract_v1" ? <NavLink className="tab-link" to={`/runs/${run.id}/contract`}>Approve the tests</NavLink> : null}
        {["overview", "watch", "journeys", "findings", "evidence", "results"].map((tab) => (
          <NavLink
            key={tab}
            to={`/runs/${run.id}/${tab}`}
            className={({ isActive }) => `tab-link ${isActive ? "active" : ""}`}
          >
            {tab === "overview" ? "Summary" : tab === "watch" ? "Watch live" : tab === "results" ? "Test results" : tab[0].toUpperCase() + tab.slice(1)}
            {tab === "findings" && results.status === "ready" ? (
              <span className="tab-count">{results.data.findings.length}</span>
            ) : null}
          </NavLink>
        ))}
        <details className="run-more-nav">
          <summary>More</summary>
          <div className="run-more-menu" aria-label="More test sections">
            {["human-action", "evaluation", "missions", "perspectives", "agents"].map((tab) => (
              <NavLink key={tab} to={`/runs/${run.id}/${tab}`} className={({ isActive }) => `tab-link ${isActive ? "active" : ""}`}>
                {tab === "human-action" ? "Human Assistance" : tab === "agents" ? "Testers & Agents" : tab[0].toUpperCase() + tab.slice(1)}
              </NavLink>
            ))}
          </div>
        </details>
      </nav>
      <HumanAssistanceHost key={`${appContext.user.id}:${appContext.workspace.id}:${appContext.workspace.role}:${run.id}`}
        context={{ ...appContext, run, results, refresh }}><Outlet
        context={{ ...appContext, run, results, refresh } satisfies RunContext}
      /></HumanAssistanceHost>
      </div>
      {!location.pathname.endsWith("/human-action") &&
      !location.pathname.endsWith("/activity") &&
      !location.pathname.endsWith("/watch") &&
      !location.pathname.endsWith("/report") &&
      !location.pathname.endsWith("/results") &&
      !location.pathname.endsWith("/contract") &&
      !location.pathname.endsWith("/evidence") ? (
        <RunFlowPanel
          runId={run.id}
          userId={appContext.user.id}
          runStatus={run.status}
          reportReady={results.status === "ready"}
        />
      ) : null}
      </div>
    </>
  );
}

import { useEffect, useRef, useState } from "react";
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
import { Banner, InlineAlert } from "../components/ui/Feedback";
import {
  ErrorPanel,
  LoadingPanel,
  Spinner,
} from "../components/ui/StateViews";
import { StatusBadge, TestStatusBadge } from "../components/ui/StatusBadge";
import { DeleteAction } from "../components/markettwin/DeleteAction";
import { canManageLifecycle, canWriteWorkspace } from "../lib/permissions";
import { Button } from "../components/ui/button";
import { ApiError, TestRun, RunResults, api } from "../lib/api";
import { CONTRACT_STAGE_STATUS, MODE_STATUS, statusEntry } from "../lib/status";
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
  const { runId = "" } = useParams();
  return <RunLayoutForRun key={runId} runId={runId} />;
}

function RunLayoutForRun({ runId }: { runId: string }) {
  const navigate = useNavigate();
  const location = useLocation();
  const appContext = useOutletContext<AppShellContext>();
  const canWrite = canWriteWorkspace(appContext.workspace.role);
  const active = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);
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
  const retiredReplay = runQuery.data?.status === "draft" &&
    Boolean(runQuery.data.configuration_snapshot.frozen_contract_source_run_id);
  const startableDraft = runQuery.data?.status === "draft" && !retiredReplay;
  const preflight = useQuery({ queryKey: ["run-preflight", appContext.user.id, runId],
    queryFn: () => api.getRunPreflight(runId), enabled: startableDraft, retry: false,
    refetchInterval: (query) => query.state.data?.checks.some(
      (check) => check.name === "app_map" && !check.ready
    ) ? 5000 : false });
  async function startRun() {
    if (starting || !startableDraft || !canWrite) return;

    setStarting(true);
    setStartError(null);

    try {
      await api.startRun(runId);
      await runQuery.refetch();
      if (active.current) navigate(`/runs/${runId}/watch`);
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
  // The mode descriptor and the header stage badge take their words from
  // lib/status.ts — the one status vocabulary (examination X-1).
  const modeKey = run.run_kind && ["explore_test", "persona", "slop"].includes(run.run_kind)
    ? run.run_kind
    : typeof run.configuration_snapshot.execution_mode === "string"
      ? run.configuration_snapshot.execution_mode
      : "legacy_persona";
  const executionMode = (MODE_STATUS[modeKey] ?? MODE_STATUS.legacy_persona).word;
  const discoveryStage = typeof run.configuration_snapshot.discovery_stage === "string"
    ? run.configuration_snapshot.discovery_stage
    : "";
  const stageEntry = CONTRACT_STAGE_STATUS[discoveryStage];
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
  const runPath = `/runs/${run.id}`;
  const summary = [runPath, `${runPath}/`, ...["overview", "results", "report"].map(tab => `${runPath}/${tab}`)].includes(location.pathname)
    || location.pathname.startsWith(`${runPath}/findings/`);
  const journeyDetail = location.pathname.startsWith(`${runPath}/journeys/`);

  return (
    <>
      <div className="study-utility">
        <Link className="back-link" to={`/applications/${run.application_id}/runs`}>
          <ArrowLeft size={16} aria-hidden="true" />
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
            {run.configuration_snapshot.execution_mode === "discovery_contract_v1" && results.status !== "ready" && stageEntry ? <StatusBadge status={discoveryStage} source="contractStage" /> : <TestStatusBadge status={run.status} />}
            {canWrite && startableDraft ? (
              <>
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
              <RefreshCw size={20} aria-hidden="true" />
            </Button>
          </div>
        }
      />
      {startError ? (
        <InlineAlert severity="error" title="Could not start the test" role="alert">
          {startError}
        </InlineAlert>
      ) : null}
      {retiredReplay ? (
        <Banner severity="warning" titleAs="h2" title="Contract replay retired" action={canWrite ? (
          <Link className="primary-button" to={`/applications/${run.application_id}/runs/new?${new URLSearchParams({
            mode: "explore_test", target: run.target_id,
          })}`}>Create a new test</Link>
        ) : undefined}>
          <p>{canWrite
            ? "Create a fresh Explore & Test run for this target. This saved draft remains available."
            : "This saved draft is read-only."}</p>
        </Banner>
      ) : null}
      {startableDraft ? <RunPreflightPanel data={preflight.data} error={preflight.error?.message} loading={preflight.isFetching} onRefresh={() => void preflight.refetch()} /> : null}
      {["queued", "planning", "running"].includes(run.status) && run.status_reason ? (
        <Banner severity="warning" titleAs="h2" title="Execution needs attention">
          <p>{run.status_reason}</p>
        </Banner>
      ) : null}
      {run.configuration_snapshot.discovery_stage === "awaiting_approval" ? <section className="panel"><h2>Contract flow retired</h2><p>This run was created with the retired contract-approval flow. Stored contract results remain available here.</p></section> : null}
      {run.status === "awaiting_human" && run.configuration_snapshot.discovery_stage !== "awaiting_approval" && !location.pathname.endsWith("/human-action") && !location.pathname.endsWith("/activity") && !location.pathname.endsWith("/watch") ? (
        <Banner severity="warning" titleAs="h2" title={<>{statusEntry("run", run.status).word} — the tester is paused</>} action={<Link className="primary-button" to={`/runs/${run.id}/watch#human-action-heading`}>Help this tester</Link>}>{run.status_reason ? <p>{run.status_reason}</p> : <p>The tester is paused until you complete or skip the affected work.</p>}</Banner>
      ) : null}
      <div className="run-workspace">
      <div className="run-workspace-content">
      <nav className="tab-strip" aria-label="Test sections">
        <Link to={`/runs/${run.id}`} aria-current={summary ? "page" : undefined} className={`tab-link ${summary ? "active" : ""}`}>Summary</Link>
        {["watch", "activity", "evidence"].map((tab) => (
          <NavLink
            key={tab}
            to={`/runs/${run.id}/${tab}`}
            aria-current={tab === "activity" && journeyDetail ? "location" : undefined}
            className={({ isActive }) => `tab-link ${isActive || (tab === "activity" && journeyDetail) ? "active" : ""}`}
          >
            {tab[0].toUpperCase() + tab.slice(1)}
          </NavLink>
        ))}
      </nav>
      <HumanAssistanceHost key={`${appContext.user.id}:${appContext.workspace.id}:${appContext.workspace.role}:${run.id}`}
        context={{ ...appContext, run, results, refresh }}><Outlet
        context={{ ...appContext, run, results, refresh } satisfies RunContext}
      /></HumanAssistanceHost>
      </div>
      {!summary ? <RunFlowPanel
        runId={run.id}
        userId={appContext.user.id}
        runStatus={run.status}
        reportReady={results.status === "ready"}
      /> : null}
      </div>
    </>
  );
}

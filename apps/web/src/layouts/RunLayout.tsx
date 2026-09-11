import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Outlet, useOutletContext, useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { PageHeader } from "../components/ui/PageHeader";
import { ErrorPanel, LoadingPanel } from "../components/ui/StateViews";
import { StatusBadge } from "../components/ui/StatusBadge";
import { DeleteAction } from "../components/markettwin/DeleteAction";
import { canManageLifecycle } from "../lib/permissions";
import { Button } from "../components/ui/button";
import { ApiError, TestRun, RunResults, api } from "../lib/api";
import { studyBrief, textValue } from "../lib/format";
import { terminalStatuses } from "../lib/results";
import { AppShellContext } from "./AppShell";

export type ResultsState =
  | { status: "loading" | "waiting"; data: null; error: null }
  | { status: "ready"; data: RunResults; error: null }
  | { status: "error"; data: null; error: string };
export interface RunContext extends AppShellContext { run: TestRun; results: ResultsState; refresh: () => void }
export function RunLayout() {
  const navigate = useNavigate();
  const appContext = useOutletContext<AppShellContext>();
  const { runId = "" } = useParams();
  const runQuery = useQuery({ queryKey: ["run", appContext.user.id, runId], queryFn: ({ signal }) => api.getRun(runId, signal),
    refetchInterval: query => query.state.data && !terminalStatuses.has(query.state.data.status) ? 5_000 : false });
  const resultsQuery = useQuery({ queryKey: ["results", appContext.user.id, runId], enabled: runQuery.data?.status === "completed",
    queryFn: async ({ signal }) => {
      try { return await api.getRunResults(runId, signal); }
      catch (error) { if (error instanceof ApiError && error.status === 409) return null; throw error; }
    }, refetchInterval: query => query.state.status !== "error" && query.state.data === null ? 5_000 : false });
  const refresh = () => { void runQuery.refetch(); if (runQuery.data?.status === "completed") void resultsQuery.refetch(); };
  if (runQuery.isPending) return <LoadingPanel label="Loading test" />;
  if (runQuery.isError) return <ErrorPanel message={runQuery.error.message} action={<Button variant="secondary" onClick={refresh}>Try again</Button>} />;
  const run = runQuery.data;
  const results: ResultsState = run.status !== "completed" ? { status: "waiting", data: null, error: null }
    : resultsQuery.isError ? { status: "error", data: null, error: resultsQuery.error.message }
    : resultsQuery.data === null ? { status: "waiting", data: null, error: null }
    : resultsQuery.data ? { status: "ready", data: resultsQuery.data, error: null }
    : { status: "loading", data: null, error: null };
  return <>
    <div className="study-utility"><Link className="back-link" to="/runs"><ArrowLeft size={15} aria-hidden="true" />All tests</Link><span className="monospace">{run.id.slice(0, 8)}</span></div>
    <PageHeader eyebrow="Test" title={studyBrief(run.configuration_snapshot)} description={`${textValue(run.target_snapshot.name, "Target")} · ${textValue(run.target_snapshot.environment, "Environment")}`} action={<div className="header-actions"><StatusBadge status={run.status} />{canManageLifecycle(appContext.workspace.role) ? <DeleteAction kind="test" id={run.id} name={studyBrief(run.configuration_snapshot)} disabled={!["draft", "completed", "failed", "cancelled"].includes(run.status)} onDeleted={() => navigate("/runs")} /> : null}<Button variant="ghost" size="icon" aria-label="Refresh test" onClick={refresh} disabled={runQuery.isFetching || resultsQuery.isFetching}><RefreshCw size={17} aria-hidden="true" /></Button></div>} />
    <nav className="tab-strip" aria-label="Test sections">{["overview", "findings", "report"].map(tab => <NavLink key={tab} to={`/runs/${run.id}/${tab}`} className={({ isActive }) => `tab-link ${isActive ? "active" : ""}`}>{tab[0].toUpperCase() + tab.slice(1)}{tab === "findings" && results.status === "ready" ? <span className="tab-count">{results.data.findings.length}</span> : null}</NavLink>)}</nav>
    <Outlet context={{ ...appContext, run, results, refresh } satisfies RunContext} />
  </>;
}

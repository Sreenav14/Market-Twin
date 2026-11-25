import { useQuery } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";
import { StopRunButton } from "../../components/markettwin/StopRunButton";
import type { RunContext } from "../../layouts/RunLayout";
import { api } from "../../lib/api";
import { canAuthorizeTarget } from "../../lib/permissions";
import { terminalTestStatuses } from "../../lib/results";
import { ReportActivity, ReportEyebrow, ReportFrame, ReportStatus, number, record, reportKind, useReportFlow } from "./ReportFrame";
import { RunReportPage } from "./RunReportPage";

function ProvisionalReport({ run, user, workspace }: RunContext) {
  const kind = reportKind({}, run);
  const flow = useReportFlow(run, user.id, false);
  const waiting = run.status === "awaiting_human" && run.configuration_snapshot.discovery_stage !== "awaiting_approval";
  const allowed = canAuthorizeTarget(workspace.role);
  const live = useQuery({
    queryKey: ["live-execution", user.id, workspace.id, workspace.role, run.id],
    queryFn: ({ signal }) => api.getLiveExecution(run.id, undefined, signal),
    enabled: allowed && run.status === "running",
    retry: false,
    refetchInterval: 5000,
  });
  const pictureUnavailable = allowed && run.status === "running" && live.data !== undefined
    && (live.data.browser?.viewer_state === "suppressed" || !live.data.browser);
  const checkpoint = run.configuration_snapshot.slop_checkpoint as {
    visited?: string[]; pending?: string[]; in_flight?: { url: string }[]; active_url?: string;
  } | undefined;
  const active = checkpoint?.in_flight?.map(page => page.url) ?? (checkpoint?.active_url ? [checkpoint.active_url] : []);
  const title = waiting ? "Waiting for you" : kind === "slop" ? "Audit running — findings so far" : "Test in progress — findings so far";
  return <ReportFrame
    takeaway={<><ReportEyebrow run={run} kind={kind} /><h2 className="report-verdict">{title}</h2>
      {waiting && run.status_reason ? <p>{run.status_reason}</p> : null}
      <Link className="primary-button" to={`/runs/${run.id}/watch${waiting ? "#human-action-heading" : ""}`}>{waiting ? "Help this tester" : "Watch live"}</Link>
      {allowed ? <StopRunButton run={run} /> : null}
      {pictureUnavailable ? <div>
        <p role="status"><ReportStatus word="Live picture unavailable" tone="notchecked" />. The test is still running. The live picture is unavailable right now.</p>
        <div className="report-controls">
          <button type="button" disabled={live.isFetching} onClick={() => void live.refetch()}>Retry the live picture</button>
          <Link to={`/runs/${run.id}/activity`}>Open Activity</Link>
        </div>
      </div> : null}
    </>}
    activity={<ReportActivity flow={flow.data} coverage={record(checkpoint)} slop={kind === "slop"} />}
    middle={<RunReportPage />}
    coverage={kind === "slop" && checkpoint ? <section className="report-section" aria-label="UI audit progress">
      <h2>Provisional coverage</h2>
      <p>Processed {number(Math.max(0, (checkpoint.visited?.length ?? 0) - active.length))} · In progress {number(active.length)} · Queued {number(checkpoint.pending?.length ?? 0)}</p>
      {active.length ? <ul aria-label="Pages being inspected">{active.map(url => <li key={url}>{url}</li>)}</ul> : null}
    </section> : null}
  />;
}

export function RunOverviewPage() {
  const context = useOutletContext<RunContext>();
  const { run, results } = context;
  if (results.status !== "waiting" || run.status === "draft" || terminalTestStatuses.has(run.status)
    || run.configuration_snapshot.discovery_stage === "awaiting_approval") return <RunReportPage />;
  return <>
    <ProvisionalReport {...context} />
    {run.configuration_snapshot.learn_task === true ? <section className="panel section-block">
      <h2>Task learning</h2><p>The app’s skill library shows whether the recorded task passed replay.</p>
      <div className="knowledge-row-actions"><Link to={`/runs/${run.id}/board`}>View the Board</Link> <Link to={`/applications/${run.application_id}/knowledge`}>View the app’s skills</Link></div>
    </section> : null}
  </>;
}

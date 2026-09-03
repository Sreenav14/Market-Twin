import { NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";

import { PageHeader } from "../components/ui/PageHeader";
import { ErrorPanel, LoadingPanel } from "../components/ui/StateViews";
import { StatusBadge } from "../components/ui/StatusBadge";
import { TestRun, api } from "../lib/api";
import { studyBrief, textValue } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { AppShellContext } from "./AppShell";

export interface RunContext extends AppShellContext {
  run: TestRun;
}

const futureTabs = ["perspectives", "missions", "journeys", "activity", "findings", "evidence", "report"] as const;

export function RunLayout() {
  const appContext = useOutletContext<AppShellContext>();
  const { runId = "" } = useParams();
  const runState = useAsync(() => api.getRun(runId), [runId]);

  if (runState.status === "loading") return <LoadingPanel label="Loading study" />;
  if (runState.status === "error") return <ErrorPanel message={runState.error} />;

  const run = runState.data;

  return (
    <>
      <PageHeader eyebrow="Study" title={studyBrief(run.configuration_snapshot)} description={`${textValue(run.target_snapshot.name, "Target")} · ${textValue(run.target_snapshot.environment, "Environment")}`} action={<StatusBadge status={run.status} />} />
      <nav className="tab-strip" aria-label="Study sections">
        <NavLink to={`/runs/${run.id}/overview`} className={({ isActive }) => isActive ? "tab-link active" : "tab-link"}>Overview</NavLink>
        {futureTabs.map((tab) => <span className="tab-link disabled" aria-disabled="true" key={tab}>{tab}</span>)}
      </nav>
      <Outlet context={{ ...appContext, run } satisfies RunContext} />
    </>
  );
}

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { testTitle } from "../../lib/format";
import { PageHeader } from "../ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../ui/StateViews";
import { TestStatusBadge } from "../ui/StatusBadge";

export function ProjectAgentBrowser({ workspaceId }: { workspaceId: string }) {
  const [projectId, setProjectId] = useState("");
  const projects = useQuery({ queryKey: ["agent-projects", workspaceId], queryFn: () => api.listApplications(workspaceId) });
  const runs = useQuery({ queryKey: ["agent-project-runs", projectId], queryFn: () => api.listRuns(projectId), enabled: Boolean(projectId), refetchInterval: 5000 });
  const project = projects.data?.find((item) => item.id === projectId);
  return <>
    <PageHeader title="Testers" description="Choose an application and test to inspect its testers, goals, actual actions and evidence. Advanced model and prompt settings remain available within each test." />
    {projects.isPending ? <LoadingPanel label="Loading applications" /> : projects.isError ? <ErrorPanel message={projects.error.message} /> : <div className="agent-project-grid">{projects.data?.map((item) => <button className={`agent-prompt-choice panel${item.id === projectId ? " is-selected" : ""}`} key={item.id} aria-pressed={item.id === projectId} onClick={() => setProjectId(item.id)}><span className="agent-project-head"><span className="product-icon small" aria-hidden="true">{item.name.slice(0, 2).toUpperCase()}</span><strong>{item.name}</strong></span><span>{item.description || "No description"}</span><span className="agent-project-open">View testers and instructions</span></button>)}</div>}
    {project ? <section className="panel"><h2>{project.name} · Tests</h2>
      {runs.isPending ? <LoadingPanel label="Loading tests" /> : runs.isError ? <ErrorPanel message={runs.error.message} /> : runs.data?.length ? <div className="study-table">{runs.data.map((run) => <Link className="study-row" key={run.id} to={`/runs/${run.id}/agents`}><span className="study-row-copy"><strong>{testTitle(run)}</strong><span>Open testers and instructions</span></span><TestStatusBadge status={run.status} /></Link>)}</div> : <EmptyState title="No tests in this application" copy="Create and start a test to record its testers." />}
    </section> : projects.data?.length ? <p className="agent-project-hint">Select an application to see its tests.</p> : !projects.isPending && !projects.isError ? <EmptyState title="No applications yet" copy="Add an application to begin testing." /> : null}
  </>;
}

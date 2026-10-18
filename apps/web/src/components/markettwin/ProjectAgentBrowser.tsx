import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { testTitle } from "../../lib/format";
import { PageHeader } from "../ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../ui/StateViews";

export function ProjectAgentBrowser({ workspaceId }: { workspaceId: string }) {
  const [projectId, setProjectId] = useState("");
  const projects = useQuery({ queryKey: ["agent-projects", workspaceId], queryFn: () => api.listApplications(workspaceId) });
  const runs = useQuery({ queryKey: ["agent-project-runs", projectId], queryFn: () => api.listRuns(projectId), enabled: Boolean(projectId), refetchInterval: 5000 });
  const project = projects.data?.find((item) => item.id === projectId);
  return <>
    <PageHeader title="Testers & Agents" description="Choose an application and test to inspect its testers, goals, actual actions and evidence. Advanced model and prompt settings remain available within each test." />
    {projects.isPending ? <LoadingPanel label="Loading projects" /> : projects.isError ? <ErrorPanel message={projects.error.message} /> : <div className="agent-project-grid">{projects.data?.map((item) => <button className={`agent-prompt-choice panel${item.id === projectId ? " is-selected" : ""}`} key={item.id} aria-pressed={item.id === projectId} onClick={() => setProjectId(item.id)}><strong>{item.name}</strong><span>View test agent flows</span></button>)}</div>}
    {project ? <section className="panel"><h2>{project.name} · Tests</h2>
      {runs.isPending ? <LoadingPanel label="Loading tests" /> : runs.isError ? <ErrorPanel message={runs.error.message} /> : runs.data?.length ? <div className="study-table">{runs.data.map((run) => <Link className="study-row" key={run.id} to={`/runs/${run.id}/agents`}><span className="study-row-copy"><strong>{testTitle(run)}</strong><span>Open ordered agent flow</span></span><span>{run.status}</span></Link>)}</div> : <EmptyState title="No tests in this project" copy="Create and start a test to record its agents." />}
    </section> : projects.data?.length ? <p className="inline-note">Select a project to see its tests.</p> : !projects.isPending && !projects.isError ? <EmptyState title="No projects yet" copy="Add an application to begin testing." /> : null}
  </>;
}

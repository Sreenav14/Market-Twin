import { Link, useOutletContext } from "react-router-dom";
import { useEffect, useState } from "react";
import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { Application, TestRun, api } from "../../lib/api";
import { studyBrief, textValue } from "../../lib/format";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function RunsPage() {
  const { workspace } = useOutletContext<AppShellContext>(); const applicationsState=useAsync(()=>api.listApplications(workspace.id),[workspace.id]); const [runs,setRuns]=useState<TestRun[]>([]); const [loadingRuns,setLoadingRuns]=useState(true); const [runsError,setRunsError]=useState<string|null>(null);
  useEffect(()=>{if(applicationsState.status!=="ready")return;let cancelled=false;setLoadingRuns(true);setRunsError(null);Promise.all(applicationsState.data.map((application:Application)=>api.listRuns(application.id))).then((groups)=>{if(!cancelled)setRuns(groups.flat());}).catch((error:unknown)=>{if(!cancelled)setRunsError(error instanceof Error?error.message:"Could not load runs.");}).finally(()=>{if(!cancelled)setLoadingRuns(false);});return()=>{cancelled=true;};},[applicationsState]);
  return <><PageHeader eyebrow="Testing activity" title="Runs" description="Every Test Run keeps the study brief and target snapshot that were used when it was created." />{applicationsState.status==="loading"||loadingRuns?<LoadingPanel label="Loading runs"/>:applicationsState.status==="error"?<ErrorPanel message={applicationsState.error}/>:runsError?<ErrorPanel message={runsError}/>:runs.length===0?<EmptyState title="No runs yet" copy="Open an application and create your first study." action={<Link className="primary-button" to="/applications">Choose application</Link>}/>:<div className="data-list">{runs.map((run)=><Link className="data-row" to={`/runs/${run.id}/overview`} key={run.id}><span className="row-icon"><Icon name="runs" size={16}/></span><div className="row-primary"><strong>{studyBrief(run.configuration_snapshot)}</strong><span>{textValue(run.target_snapshot.name,textValue(run.target_snapshot.base_url,"Target"))}</span></div><StatusBadge status={run.status}/><Icon name="arrow" size={16}/></Link>)}</div>}</>;
}

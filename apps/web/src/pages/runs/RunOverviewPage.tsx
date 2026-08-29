import { useOutletContext } from "react-router-dom";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { textValue } from "../../lib/format";
import { RunContext } from "../../layouts/RunLayout";

export function RunOverviewPage() {
  const { run } = useOutletContext<RunContext>();
  const stageIndex = run.status === "completed" ? 3 : run.status === "queued" || run.status === "running" ? 2 : run.status === "planning" ? 1 : 0;
  const stages = ["Created", "Planning", "Execution", "Findings"];
  return <><section className="run-progress" aria-label="Study progress"><div className="run-progress-track">{stages.map((stage,index)=><span className={index<=stageIndex?"complete":""} key={stage}/>)}</div><div className="run-stage-grid">{stages.map((stage,index)=><div key={stage}><strong>{stage}</strong><span>{index===0?"Study persisted":index<=stageIndex?run.status:"Waiting"}</span></div>)}</div></section><div className="detail-grid section-block"><section className="panel"><div className="section-heading compact-heading"><div><p className="eyebrow">Configuration</p><h2>Study details</h2></div><StatusBadge status={run.status}/></div><dl className="definition-list"><div><dt>Target</dt><dd>{textValue(run.target_snapshot.name,"Target")}</dd></div><div><dt>Environment</dt><dd>{textValue(run.target_snapshot.environment)}</dd></div><div><dt>Authentication</dt><dd>{run.target_snapshot.requires_auth?"Protected":"Public"}</dd></div><div><dt>Run ID</dt><dd className="monospace">{run.id}</dd></div></dl></section><aside className="info-card"><span className="future-kicker">Current backend state</span><h2>Planning is not connected yet.</h2><p>The Run is real and persisted. Perspectives, missions, journeys, execution, evidence, and findings remain disabled until those backend stages are implemented.</p></aside></div></>;
}

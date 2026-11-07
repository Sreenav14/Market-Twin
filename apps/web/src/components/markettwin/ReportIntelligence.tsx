import { useId, useLayoutEffect, useRef } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { api, request, type Finding, type JourneyDetail, type JourneyExecution, type RunResults, type TestRun } from '../../lib/api';
import { asRecord, findingClassification, isConfirmedFinding, severityOrder, sortFindings } from '../../lib/results';
import { assertionObservation, journeyBlocker } from '../../lib/journeyPresentation';
import { countCategories, findingStepHref, outcomeCounts, outcomeLabels, recordedTasks, taskOutcome, taskOutcomes, verificationGroup } from '../../lib/reportIntelligence';
import { ArtifactEvidence } from '../../pages/runs/FindingDetailPage';
import { EmptyState, ErrorPanel, LoadingPanel } from '../ui/StateViews';
import { StatusBadge } from '../ui/StatusBadge';
import { statusLabel } from '../../lib/format';

export type ReportView = 'overview' | 'usefulness' | 'inspection';
export function reportView(value: string | null): ReportView {
  return value === 'usefulness' || value === 'inspection' ? value : 'overview';
}
const views: [ReportView, string][] = [['overview','Report overview'],['usefulness','Application usefulness'],['inspection','UI/UX & functional inspection']];

// Search-param callbacks do not queue like React state setters. Compose rapid
// changes against the latest submitted parameters while navigation commits.
function useReportSearch() {
  const [params,navigate]=useSearchParams();
  const current=useRef(params);
  useLayoutEffect(()=>{current.current=params;},[params]);
  const update=(change:(previous:URLSearchParams)=>URLSearchParams,_options?:{replace?:boolean})=>{
    const next=change(new URLSearchParams(current.current));
    current.current=next;
    navigate(next,{replace:true});
  };
  return [params,update] as const;
}

export function ReportNavigation({view}: {view: ReportView}) {
  const [params] = useSearchParams();
  return <nav className="report-destinations" aria-label="Report views">{views.map(([key,label])=>{
    const next=new URLSearchParams(params);next.set('reportView',key);
    return <Link key={key} to={{search:next.toString()}} aria-current={view===key?'page':undefined}>{label}</Link>;
  })}</nav>;
}

export function CountBars({title,rows,selected,onSelect,tone='blue',denominator}: {
  title:string; rows:{key:string;label:string;count:number}[]; selected?:string;
  onSelect:(key:string)=>void; tone?:string; denominator?:number;
}) {
  const id=useId();const max=Math.max(denominator??rows.reduce((total,row)=>total+row.count,0),...rows.map(row=>row.count));
  return <section className="report-count-chart" aria-labelledby={id}><h3 id={id}>{title}</h3>
    <p className="chart-help">Recorded count · axis 0–{max.toLocaleString()} · select a row to inspect</p>
    <ul>{rows.map(row=><li key={row.key}><button type="button" className={`count-bar count-${tone} outcome-${row.key}`} aria-pressed={selected===row.key}
      onClick={()=>onSelect(row.key)} title={`${row.label}: ${row.count} recorded ${row.count===1?'item':'items'}`}>
      <span className="count-bar-label">{row.label}</span>{' '}<strong>{row.count.toLocaleString()}</strong>
      <span className="count-bar-track" aria-hidden="true"><span style={{width:`${max?row.count/max*100:0}%`}} /></span>
    </button></li>)}</ul><div className="count-axis" aria-hidden="true"><span>0</span><span>{max.toLocaleString()}</span></div>
  </section>;
}

function RecordedFlow({runId,userId,journey}: {runId:string;userId:string;journey:JourneyExecution}) {
  const [params,setParams]=useReportSearch();
  const detail=useInfiniteQuery({queryKey:['report-step-flow',userId,runId,journey.id],initialPageParam:0,
    queryFn:({pageParam,signal})=>request<JourneyDetail>(`/api/v1/test-runs/${runId}/journeys/${journey.id}?after_step=${pageParam}`,{signal}),
    getNextPageParam:(page,_pages,cursor,cursors)=>page.next_after_step!==null&&page.next_after_step>cursor&&!cursors.includes(page.next_after_step)?page.next_after_step:undefined,
  });
  const steps=[...new Map((detail.data?.pages.flatMap(page=>page.steps)??[]).map(step=>[step.id,step])).values()].sort((a,b)=>a.step_number-b.step_number);
  const requestedStep=params.get('reportStep');
  const selected=steps.find(step=>String(step.id)===requestedStep)??(requestedStep?undefined:steps[0]);
  const assertion=assertionObservation(selected?.observation_summary??null);
  const artifacts=[...new Map((detail.data?.pages.flatMap(page=>page.artifacts)??[]).map(artifact=>[artifact.id,artifact])).values()].filter(artifact=>artifact.step_id===selected?.id);
  return <section className="report-workflow" aria-labelledby="report-workflow-heading"><div className="section-heading"><div>
    <h3 id="report-workflow-heading">Observed workflow</h3><p>{journey.mission_title}</p></div>
    <Link className="text-link" to={`/runs/${runId}/journeys/${journey.id}`}>Full journey and evidence</Link></div>
    {detail.isPending?<LoadingPanel label="Loading recorded steps"/>:detail.isError?<ErrorPanel message="Recorded steps could not be loaded."
      action={<button className="secondary-button" onClick={()=>void detail.refetch()}>Retry recorded steps</button>}/>:!steps.length?<p>No executed steps were recorded. Planned steps are not inferred.</p>:<>
      <p className="chart-help">{steps.length} loaded steps{detail.hasNextPage?' · Partial sequence':''}. Nodes are recorded actions, not a sitemap.</p>
      {requestedStep&&!selected?<p className="report-data-limit">The requested step is not in the loaded records.{detail.hasNextPage?' Load more recorded steps to continue.':' Select an available step below.'}</p>:null}
      <ol className="report-step-flow" aria-label="Recorded workflow steps">{steps.map(step=><li key={step.id}><button type="button" aria-pressed={selected?.id===step.id}
        onClick={()=>setParams(previous=>{const next=new URLSearchParams(previous);next.set('reportStep',String(step.id));return next;},{replace:true})}>
        <span>Step {step.step_number}</span><strong>{step.action_summary}</strong><span>{step.status.replaceAll('_',' ')}</span>
      </button></li>)}</ol>
      {detail.hasNextPage?<button className="secondary-button" disabled={detail.isFetchingNextPage} onClick={()=>void detail.fetchNextPage()}>{detail.isFetchingNextPage?'Loading steps…':'Load more recorded steps'}</button>:null}
      {selected?<section className="report-step-detail" data-assertion={assertion?.status} aria-label="Selected recorded step" aria-live="polite"><div className="section-heading"><h4>{selected.action_summary}</h4><StatusBadge status={selected.status} source="journeyExecution"/></div>
        {assertion?<dl className="report-value-comparison"><div><dt>Expected</dt><dd>{assertion.expected}</dd></div><div><dt>Observed</dt><dd>{assertion.observed}</dd></div></dl>
          :<p>{selected.observation_summary||'No observation was recorded for this step.'}</p>}
        <p className="muted">{selected.started_at?<time dateTime={selected.started_at}>{new Date(selected.started_at).toLocaleString()}</time>:'Timestamp not recorded'} · Step ID {selected.id}</p>
        <Link className="text-link" to={`/runs/${runId}/journeys/${journey.id}?step=${selected.id}`}>Inspect this step and supporting evidence</Link>
        {artifacts.length?<div className="report-artifacts">{artifacts.map(artifact=><ArtifactEvidence key={artifact.id} runId={runId} artifactId={artifact.id}/>)}</div>:<p className="muted">No artifact is linked to this loaded step.</p>}
      </section>:null}
    </>}
  </section>;
}

function FindingInspection({run,results,tasks}: {run:TestRun;results:RunResults;tasks:JourneyExecution[]}) {
  const [params,setParams]=useReportSearch();
  const category=params.get('category')??'all',severity=params.get('severity')??'all',verification=params.get('verification')??'all';
  const task=params.get('findingTask')??'all',search=params.get('findingSearch')??'',sort=params.get('findingSort')??'severity';
  const set=(key:string,value:string)=>setParams(previous=>{const next=new URLSearchParams(previous);if(value&&value!=='all')next.set(key,value);else next.delete(key);next.delete('finding');return next;},{replace:true});
  const base=results.findings.filter(finding=>(verification==='all'||verificationGroup(finding)===verification)
    &&(task==='all'||finding.journey_ids.includes(task))
    &&`${finding.title} ${finding.summary}`.toLowerCase().includes(search.toLowerCase()));
  const filtered=sortFindings(base.filter(finding=>(category==='all'||finding.category===category)&&(severity==='all'||finding.severity===severity)),sort);
  const selected=filtered.find(finding=>finding.id===params.get('finding'))??filtered[0];
  const clear=()=>setParams(previous=>{const next=new URLSearchParams(previous);for(const key of ['category','severity','verification','findingTask','findingSearch','findingSort','finding'])next.delete(key);return next;},{replace:true});
  return <section className="report-inspection" aria-labelledby="report-inspection-heading"><header className="report-analysis-heading"><h2 id="report-inspection-heading">UI/UX & functional inspection</h2>
    <p>Explore recorded findings. Verification, severity and execution limitations remain separate.</p></header>
    {results.findings.length?<div className="report-chart-grid"><CountBars title="Findings by category" rows={countCategories(base.filter(finding=>severity==='all'||finding.severity===severity))} selected={category} onSelect={value=>set('category',category===value?'all':value)}/>
      <CountBars title="Findings by severity" rows={severityOrder.map(key=>({key,label:key,count:base.filter(finding=>(category==='all'||finding.category===category)&&finding.severity===key).length}))} selected={severity} tone="severity" onSelect={value=>set('severity',severity===value?'all':value)}/></div>:<p className="report-data-limit">No findings were recorded. This does not establish that the tested product is issue-free.</p>}
    <div className="report-filter-bar"><label>Search findings<input value={search} onChange={event=>set('findingSearch',event.target.value)} type="search"/></label>
      <label>Category<select value={category} onChange={event=>set('category',event.target.value)}><option value="all">All categories</option>{countCategories(results.findings).map(item=><option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
      <label>Severity<select value={severity} onChange={event=>set('severity',event.target.value)}><option value="all">All severities</option>{severityOrder.map(item=><option key={item}>{item}</option>)}</select></label>
      <label>Verification<select value={verification} onChange={event=>set('verification',event.target.value)}><option value="all">All classifications</option><option value="verified">Verified issues</option><option value="unverified">Needs verification</option><option value="execution">Execution issues</option></select></label>
      <label>Related task<select value={task} onChange={event=>set('findingTask',event.target.value)}><option value="all">All linked tasks</option>{tasks.map(item=><option key={item.id} value={item.id}>{item.mission_title}</option>)}</select></label>
      <label>Prioritize by<select value={sort} onChange={event=>set('findingSort',event.target.value)}><option value="severity">Recorded severity</option><option value="journeys">Linked journey count</option></select></label>
      <button className="secondary-button" onClick={clear}>Reset finding filters</button></div>
    <p role="status" className="report-filter-result">{filtered.length} matching {filtered.length===1?'finding':'findings'} · {category==='all'?'All categories':category.replaceAll('_',' ')} · {severity==='all'?'All severities':severity}</p>
    <div className="report-inspection-workbench"><ul className="report-finding-index" aria-label="Filtered findings">{filtered.map(finding=><li key={finding.id}><button type="button" aria-pressed={selected?.id===finding.id}
      onClick={()=>setParams(previous=>{const next=new URLSearchParams(previous);next.set('finding',finding.id);return next;},{replace:true})}><span>{finding.severity} · {finding.category.replaceAll('_',' ')}</span><strong>{finding.title}</strong><span>{statusLabel(findingClassification(finding))}</span></button></li>)}</ul>
      {selected?<FindingDetail key={selected.id} finding={selected} runId={run.id} tasks={tasks}/>:<p>No findings match these filters. Reset the filters to review all recorded findings.</p>}
    </div><details className="report-method-note"><summary>Page coverage, priority and evidence limits</summary><p>The report has no authoritative page-inspection inventory. Findings are filtered by their recorded category, severity and linked tasks. A visited page is not proof of a completed inspection.</p><p>Linked journey count measures recorded reach, not real user impact. Implementation effort and impact-versus-effort scores were not recorded. Screenshot regions are not inferred.</p></details>
  </section>;
}

function FindingDetail({finding,runId,tasks}: {finding:Finding;runId:string;tasks:JourneyExecution[]}) {
  return <article className="report-finding-detail" aria-label="Selected finding" aria-live="polite"><p className="section-label">{statusLabel(findingClassification(finding))} · {finding.severity}</p><h3>{finding.title}</h3>
    <h4>What happened</h4><p>{finding.summary}</p><h4>Who is affected</h4>
    <ul>{finding.journey_ids.map(id=><li key={id}><Link to={`/runs/${runId}/journeys/${id}`}>{tasks.find(item=>item.id===id)?.mission_title??`Recorded journey ${id.slice(0,8)}`}</Link></li>)}</ul>
    {!finding.journey_ids.length?<p>No affected journey was linked.</p>:null}<p className="muted">Wider customer impact was not measured.</p>
    <h4>Recommended improvement</h4><p>{finding.recommendation||'No recommendation was recorded.'}</p>
    <Link className="text-link" to={findingStepHref(runId,finding)}>{finding.journey_ids.length===1&&finding.evidence.step_ids.length?'Open supporting step':'Open finding and linked evidence'}</Link>
    <div className="report-artifacts">{finding.evidence.artifact_ids.map(id=><ArtifactEvidence key={id} runId={runId} artifactId={id}/>)}</div>
    {!finding.evidence.artifact_ids.length?<p className="muted">No artifact is linked to this finding.</p>:null}
  </article>;
}

export function ReportAnalytics({run,results,userId,view}: {run:TestRun;results:RunResults;userId:string;view:ReportView}) {
  const [params,setParams]=useReportSearch();
  const feature=run.configuration_snapshot.execution_mode==='deep_feature_v1'||results.report.payload.mode==='deep_feature_v1';
  const journeys=useQuery({queryKey:['report-journeys',userId,run.workspace_id,run.id],queryFn:({signal})=>api.getRunJourneys(run.id,signal)});
  const tasks=recordedTasks(Array.isArray(journeys.data)?journeys.data:[],feature);
  const outcome=params.get('outcome')??'all',persona=params.get('persona')??'all';
  const filtered=tasks.filter(task=>(outcome==='all'||taskOutcome(task)===outcome)&&(persona==='all'||task.persona_name===persona));
  const selected=filtered.find(task=>task.id===params.get('journey'))??filtered[0];
  const go=(nextView:ReportView,key?:string,value?:string)=>setParams(previous=>{const next=new URLSearchParams(previous);next.set('reportView',nextView);if(key){if(value&&value!=='all')next.set(key,value);else next.delete(key);}next.delete('reportStep');return next;},{replace:true});
  const assessment=asRecord(results.report.payload.assessment);
  const individual=assessment.status==='completed'&&Array.isArray(assessment.individual_results)?assessment.individual_results.map(asRecord):[];
  const selectedAssessment=selected?.execution_status==='completed'?individual.find(item=>item.journey_id===selected.id):undefined;
  const counts=outcomeCounts(tasks);
  if(view==='inspection')return <>{journeys.isError?<p className="report-data-limit" role="alert">Related task labels could not be loaded. Saved findings and their evidence remain available. <button className="text-link" onClick={()=>void journeys.refetch()}>Retry related tasks</button></p>:null}<FindingInspection run={run} results={results} tasks={tasks}/></>;
  return <section className={`report-analytics report-analytics-${view}`} aria-label={view==='overview'?'Report outcome analysis':'Application usefulness analysis'}>
    {journeys.isPending?<LoadingPanel label="Loading recorded task outcomes"/>:journeys.isError?<ErrorPanel message="Recorded task outcomes are unavailable. Saved findings remain available."
      action={<button className="secondary-button" onClick={()=>void journeys.refetch()}>Retry task outcomes</button>}/>:view==='overview'?<>
      <div className="report-chart-grid"><CountBars title="Recorded task outcomes" rows={counts} onSelect={value=>go('usefulness','outcome',value)} tone="outcome"/>
        <section className="report-review-priorities"><h3>Where to focus</h3><p><strong>{tasks.length}</strong> recorded task {tasks.length===1?'execution':'executions'} · {tasks.filter(task=>task.evidence_available).length} with artifacts.</p>
          <p><strong>{results.findings.filter(item=>isConfirmedFinding(item)&&['critical','high'].includes(item.severity)).length}</strong> verified critical or high-severity findings.</p>
          <button className="primary-button" onClick={()=>go('inspection')}>Inspect findings and evidence</button>
          <p className="chart-help">One latest record per journey; discovery and bootstrap work excluded. Blocked and untested tasks are never counted as passed. Counts describe synthetic tests, not customer conversion.</p>
        </section></div>
      <details className="report-method-note"><summary>Coverage and historical comparison limits</summary><p>Recorded task outcomes are derived from saved journey records. The report may contain a different aggregate scope; missing or inconsistent completion data keeps the report verdict limited.</p><p>Inspected page counts, measured performance and validated historical comparisons are not available in the current report contract. No trend or page-coverage percentage is inferred.</p></details>
    </>:<>
      <header className="report-analysis-heading"><h2>Application usefulness</h2><p>Compare recorded tasks and inspect how each goal was evaluated. These are simulated testing perspectives, not human research.</p></header>
      {feature?<p className="report-data-limit">This test uses planned feature cases. No tester usefulness score is inferred.</p>:null}
      <div className="report-usefulness-layout"><CountBars title="Task outcomes" rows={counts} selected={outcome} onSelect={value=>go('usefulness','outcome',outcome===value?'all':value)} tone="outcome"/>
        <div><div className="report-filter-bar"><label>Outcome<select value={outcome} onChange={event=>go('usefulness','outcome',event.target.value)}><option value="all">All outcomes</option>{taskOutcomes.map(item=><option key={item} value={item}>{outcomeLabels[item]}</option>)}</select></label>
          {!feature?<label>Recorded tester<select value={persona} onChange={event=>go('usefulness','persona',event.target.value)}><option value="all">All recorded testers</option>{[...new Set(tasks.map(item=>item.persona_name))].map(name=><option key={name}>{name}</option>)}</select></label>:null}
          <button className="secondary-button" onClick={()=>setParams(previous=>{const next=new URLSearchParams(previous);for(const key of ['outcome','persona','journey','reportStep'])next.delete(key);return next;},{replace:true})}>Reset task filters</button></div>
        <p role="status">{filtered.length} of {tasks.length} recorded tasks</p><div className="report-table-scroll"><table className="report-task-table"><caption>{feature?'Case execution comparison':'Tester and task comparison'}</caption><thead><tr><th scope="col">{feature?'Recorded task':'Tester / task'}</th><th scope="col">Outcome</th><th scope="col">Steps</th><th scope="col">Explore</th></tr></thead><tbody>
          {filtered.map(task=><tr key={task.id} data-selected={selected?.id===task.id}><th scope="row">{!feature?<span>{task.persona_name}</span>:null}<strong>{task.mission_title}</strong></th><td>{outcomeLabels[taskOutcome(task)]}</td><td>{Number.isFinite(task.step_count)?task.step_count.toLocaleString():'Unavailable'}</td><td><button className="text-link" aria-pressed={selected?.id===task.id} onClick={()=>go('usefulness','journey',task.id)}>Explore task</button></td></tr>)}
        </tbody></table></div>{!filtered.length?<EmptyState title="No matching recorded tasks" copy="Reset filters to inspect all available task records."/>:null}</div></div>
      {selected?<><section className="report-task-assessment"><h3>{selected.mission_title}</h3><p>{selected.mission_objective||'No task objective was recorded.'}</p>
        {journeyBlocker(selected)?<p className="report-data-limit">{journeyBlocker(selected)}</p>:null}
        {selectedAssessment?<><p><strong>Qualitative goal assessment:</strong> {statusLabel(String(selectedAssessment.goal_outcome??'inconclusive'))}</p>
          <details className="report-method-note"><summary>Saved assessment details</summary><p>Model label for ease of use: {statusLabel(String(selectedAssessment.ease_of_use??'inconclusive'))}</p></details>
          <p>{typeof selectedAssessment.summary==='string'?selectedAssessment.summary:'No assessment summary was recorded.'}</p>
          {Array.isArray(selectedAssessment.recommendations)?<ul>{selectedAssessment.recommendations.filter((item):item is string=>typeof item==='string').map((item,index)=><li key={index}>{item}</li>)}</ul>:null}
          <p className="chart-help">Model assessment of saved evidence; not a measured usefulness score.</p></>:<p className="muted">A usable qualitative assessment was not recorded for this task. No usefulness or ease-of-use score is inferred.</p>}
      </section><RecordedFlow key={selected.id} runId={run.id} userId={userId} journey={selected}/></>:null}
    </>}
  </section>;
}

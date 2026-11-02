import { describe, expect, it } from 'vitest';
import type { Finding, JourneyExecution } from './api';
import { findingStepHref, outcomeCounts, recordedTasks, taskOutcome, verificationGroup } from './reportIntelligence';

const journey=(patch:Partial<JourneyExecution>={}):JourneyExecution=>({id:'journey',ordinal:1,persona_name:'Tester',persona_perspective:'Recorded perspective',mission_title:'Save preferences',mission_objective:'Preference remains saved',step_count:3,artifact_count:1,evidence_available:true,summary:null,success_criteria:[],execution_id:'execution',attempt_number:1,execution_status:'completed',outcome:'passed',started_at:null,completed_at:null,error_message:null,result:null,...patch});
describe('recorded task outcome boundaries',()=>{
  it('never converts runtime failures, skipped work or missing execution into a passed task',()=>{
    for(const status of ['failed','timed_out','policy_blocked'])expect(taskOutcome(journey({execution_status:status,outcome:'passed'}))).toBe('blocked');
    expect(taskOutcome(journey({execution_status:'skipped',outcome:'passed'}))).toBe('not_tested');
    expect(taskOutcome(journey({execution_id:null,outcome:'passed'}))).toBe('not_tested');
    expect(taskOutcome(journey({execution_status:'running',outcome:'passed'}))).toBe('inconclusive');
    expect(taskOutcome(journey({outcome:null}))).toBe('inconclusive');
    expect(taskOutcome(journey({outcome:'failed'}))).toBe('failed');
  });
  it('excludes discovery and bootstrap, deduplicates stable journeys, and partitions the whole denominator',()=>{
    const tasks=recordedTasks([journey(),journey(),journey({id:'discovery',ordinal:10000}),journey({id:'bootstrap',runtime_name:'human_auth_bootstrap_v1'}),journey({id:'blocked',execution_status:'policy_blocked'}),journey({id:'untested',execution_id:null}),journey({id:'failed',outcome:'failed'}),journey({id:'unknown',outcome:null})],true);
    const counts=outcomeCounts(tasks);
    expect(tasks).toHaveLength(5);
    expect(counts.map(row=>row.count)).toEqual([1,1,1,1,1]);
    expect(counts.reduce((sum,row)=>sum+row.count,0)).toBe(tasks.length);
  });
});
it('preserves verification and avoids fabricating a multi-journey evidence association',()=>{
  const finding={id:'finding',finding_kind:'observed_product_issue',verification_status:'verified_deterministic',evidence:{step_ids:[13],artifact_ids:['artifact']},journey_ids:['first','second']} as Finding;
  expect(verificationGroup(finding)).toBe('verified');
  expect(findingStepHref('run',finding)).toBe('/runs/run/findings/finding');
  expect(findingStepHref('run',{...finding,journey_ids:['first']})).toBe('/runs/run/journeys/first?step=13');
  expect(verificationGroup({...finding,verification_status:'unverified'})).toBe('unverified');
});

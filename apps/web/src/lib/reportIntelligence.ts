import type { Finding, JourneyExecution } from './api';
import { journeyIdentity } from './journeyPresentation';
import { findingClassification, isConfirmedFinding } from './results';

export const taskOutcomes = ['passed', 'failed', 'blocked', 'not_tested', 'inconclusive'] as const;
export type TaskOutcome = typeof taskOutcomes[number];
export const outcomeLabels: Record<TaskOutcome, string> = {
  passed: 'Passed', failed: 'Failed', blocked: 'Blocked', not_tested: 'Not tested', inconclusive: 'Inconclusive',
};

export function taskOutcome(journey: JourneyExecution): TaskOutcome {
  if (!journey.execution_id || journey.execution_status === 'skipped'
    || (journey.execution_status === 'cancelled' && journey.step_count === 0)) return 'not_tested';
  if (['failed', 'policy_blocked', 'timed_out', 'cancelled'].includes(journey.execution_status ?? '')) return 'blocked';
  if (journey.execution_status !== 'completed') return 'inconclusive';
  if (journey.outcome === 'passed') return 'passed';
  if (journey.outcome === 'failed') return 'failed';
  return 'inconclusive';
}

export function recordedTasks(journeys: JourneyExecution[], featureMode: boolean) {
  const seen = new Set<string>();
  return journeys.filter(journey => {
    if (!journey || typeof journey.id !== 'string' || seen.has(journey.id)
      || journeyIdentity(journey, featureMode).discovery) return false;
    seen.add(journey.id);
    return true;
  });
}

export function outcomeCounts(tasks: JourneyExecution[]) {
  return taskOutcomes.map(key => ({key, label: outcomeLabels[key], count: tasks.filter(task => taskOutcome(task) === key).length}));
}

export function verificationGroup(finding: Finding) {
  return isConfirmedFinding(finding) ? 'verified'
    : findingClassification(finding) === 'Test execution issue' ? 'execution' : 'unverified';
}

export function findingStepHref(runId: string, finding: Finding) {
  return finding.journey_ids.length === 1 && finding.evidence.step_ids.length
    ? `/runs/${runId}/journeys/${finding.journey_ids[0]}?step=${finding.evidence.step_ids[0]}`
    : `/runs/${runId}/findings/${finding.id}`;
}

export function countCategories(findings: Finding[]) {
  const counts = new Map<string, number>();
  for (const finding of findings) counts.set(finding.category, (counts.get(finding.category) ?? 0) + 1);
  return [...counts].sort(([a], [b]) => a.localeCompare(b)).map(([key, count]) => ({key, label: key.replaceAll('_', ' '), count}));
}

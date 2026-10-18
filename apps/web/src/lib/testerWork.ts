import type { JourneyExecution } from "./api";
import { journeyIdentity } from "./journeyPresentation";

// Simulated testers and missions exist only for persona journeys. Browser
// discovery records and deterministic Feature Cases are excluded.
export function simulatedTesterJourneys(journeys: JourneyExecution[], featureCaseMode: boolean): JourneyExecution[] {
  if (featureCaseMode) return [];
  return journeys.filter((journey) => !journeyIdentity(journey, false).discovery);
}

export interface JourneyGroup {
  key: string;
  journeys: JourneyExecution[];
}

export function groupJourneys(journeys: JourneyExecution[], keyOf: (journey: JourneyExecution) => string): JourneyGroup[] {
  const groups = new Map<string, JourneyGroup>();
  for (const journey of journeys) {
    const key = keyOf(journey);
    const existing = groups.get(key);
    if (existing) existing.journeys.push(journey);
    else groups.set(key, { key, journeys: [journey] });
  }
  return [...groups.values()];
}

// Summarizes recorded values exactly as stored, without inventing a missing state.
export function countLabels(values: (string | null)[]): string {
  const counts = new Map<string, number>();
  for (const value of values) {
    const label = value ? value.replaceAll("_", " ") : "not recorded";
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return [...counts].map(([label, count]) => `${count} ${label}`).join(" · ");
}

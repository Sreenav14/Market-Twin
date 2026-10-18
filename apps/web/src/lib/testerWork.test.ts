import { expect, it } from "vitest";
import type { JourneyExecution } from "./api";
import { countLabels, groupJourneys, simulatedTesterJourneys } from "./testerWork";

function journey(overrides: Partial<JourneyExecution>): JourneyExecution {
  return {
    id: "journey-1", ordinal: 1, persona_name: "New visitor", persona_perspective: "Arrives from search.",
    mission_title: "Create account", mission_objective: "Sign up.", step_count: 0, artifact_count: 0,
    evidence_available: false, summary: null, success_criteria: [], execution_id: null, attempt_number: 1,
    execution_status: "completed", outcome: "passed", started_at: null, completed_at: null, error_message: null, result: null,
    ...overrides,
  };
}

it("excludes browser discovery records from simulated testers", () => {
  const discovery = journey({ id: "discovery", ordinal: 10000, runtime_name: "browser_discovery_v1", persona_name: "Discovery" });
  const tester = journey({ id: "tester" });
  expect(simulatedTesterJourneys([discovery, tester], false).map((item) => item.id)).toEqual(["tester"]);
});

it("returns no simulated testers for deterministic Feature Cases", () => {
  expect(simulatedTesterJourneys([journey({ id: "case", result: { mode: "deep_feature_v1", case_id: "c1" } })], true)).toEqual([]);
});

it("groups journeys by a key while preserving their order", () => {
  const groups = groupJourneys([
    journey({ id: "a", mission_title: "Search" }),
    journey({ id: "b", mission_title: "Checkout" }),
    journey({ id: "c", mission_title: "Search" }),
  ], (item) => item.mission_title);
  expect(groups.map((group) => [group.key, group.journeys.map((item) => item.id)])).toEqual([
    ["Search", ["a", "c"]],
    ["Checkout", ["b"]],
  ]);
});

it("summarizes recorded values without inventing missing states", () => {
  expect(countLabels(["completed", "completed", null, "policy_blocked"])).toBe("2 completed · 1 not recorded · 1 policy blocked");
});

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ASSERTION_STATUS,
  CONTRACT_STAGE_STATUS,
  CRITERION_STATUS,
  EVALUATION_STATUS,
  EXECUTION_STATUS,
  FINDING_STATUS,
  FLOW_STATUS,
  HARNESS_ITEM_STATUS,
  INFRA_STATUS,
  JOURNEY_EXECUTION_STATUS,
  JOURNEY_OUTCOME_STATUS,
  LIFECYCLE_STATUS,
  MODE_STATUS,
  RUN_STATUS,
  SEVERITY_STATUS,
  statusEntry,
} from "./status";
import type { StatusEntry, StatusSource } from "./status";

const MAPS: Record<StatusSource, Record<string, StatusEntry>> = {
  run: RUN_STATUS,
  harnessItem: HARNESS_ITEM_STATUS,
  journeyOutcome: JOURNEY_OUTCOME_STATUS,
  journeyExecution: JOURNEY_EXECUTION_STATUS,
  execution: EXECUTION_STATUS,
  severity: SEVERITY_STATUS,
  infra: INFRA_STATUS,
  contractStage: CONTRACT_STAGE_STATUS,
  finding: FINDING_STATUS,
  assertion: ASSERTION_STATUS,
  criterion: CRITERION_STATUS,
  evaluation: EVALUATION_STATUS,
  lifecycle: LIFECYCLE_STATUS,
  mode: MODE_STATUS,
  flow: FLOW_STATUS,
};

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("status language", () => {
  it("maps every value in each source union", () => {
    for (const [source, map] of Object.entries(MAPS)) {
      for (const [value, expected] of Object.entries(map)) {
        const entry = statusEntry(source as StatusSource, value);
        expect(entry.word).toBe(expected.word);
        expect(entry.tone).toBe(expected.tone);
        expect(entry.word.length).toBeGreaterThan(0);
      }
    }
  });

  it("uses the decided words for the harness vocabularies", () => {
    expect(statusEntry("run", "awaiting_human")).toEqual({
      word: "Needs you",
      tone: "couldnot",
    });
    expect(statusEntry("harnessItem", "worked").word).toBe("Worked");
    expect(statusEntry("harnessItem", "could_not_check").word).toBe(
      "Could not check",
    );
    expect(statusEntry("harnessItem", "pending").word).toBe("Pending");
    expect(statusEntry("harnessItem", "running").word).toBe("Running");
    expect(statusEntry("harnessItem", "needs_human_login").word).toBe(
      "Needs your login",
    );
    expect(statusEntry("journeyOutcome", "passed").word).toBe("Worked");
    expect(statusEntry("journeyOutcome", "partial").word).toBe("Partly done");
    expect(statusEntry("execution", "timed_out").word).toBe("Timed out");
    expect(statusEntry("execution", "skipped").word).toBe("Skipped");
    expect(statusEntry("severity", "critical").tone).toBe("broken");
    expect(statusEntry("severity", "medium").tone).toBe("couldnot");
    expect(statusEntry("infra", "connected_relay_off").word).toBe(
      "Kafka connected · relay off",
    );
  });

  it("throws for an unknown value in development", () => {
    expect(() => statusEntry("run", "somehow_done")).toThrow(
      "Unmapped run status: somehow_done",
    );
    expect(() => statusEntry("harnessItem", "doneish")).toThrow(
      "Unmapped harnessItem status: doneish",
    );
  });

  it("falls back to the raw value with the Not checked tone in production", () => {
    // @ts-expect-error — Vite types DEV as boolean in ImportMetaEnv; the empty-string stub is deliberate (exercises the unset path) and valid at runtime under vitest 4.
    vi.stubEnv("DEV", "");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(statusEntry("run", "somehow_done")).toEqual({
      word: "somehow_done",
      tone: "notchecked",
    });
    expect(warn).toHaveBeenCalledWith("Unmapped run status: somehow_done");
  });
});

import { describe, expect, it } from "vitest";
import type { JourneyDetail, JourneyExecution } from "./api";
import { assertionObservation, initialJourneyStep, journeyBlocker, journeyIdentity } from "./journeyPresentation";

describe("journey presentation evidence", () => {
  it("explains typed assertion values without dumping internal metadata", () => {
    const summary = JSON.stringify({ assertion_id: "enabled", oracle: "enabled", status: "not_satisfied",
      expected_value: true, observed_value: false, execution_id: "internal-id" });
    expect(assertionObservation(summary)).toEqual({ id: "enabled", oracle: "enabled",
      status: "not_satisfied", expected: "true", observed: "false", reason: null });
    expect(assertionObservation("BrowserActionError")).toBeNull();
    expect(assertionObservation('{"status":"failed"}')).toBeNull();
    expect(assertionObservation("null")).toBeNull();
  });
  it("selects the first recorded failure and preserves an ordinary first step fallback", () => {
    const step = (id: number, status: string, observation_summary: string | null = null): JourneyDetail["steps"][number] => ({
      id, step_number: id, action_type: "click", action_summary: "Click Agent", status,
      observation_summary, started_at: null, completed_at: null,
    });
    const first = step(1, "completed"), failed = step(2, "failed"), later = step(3, "policy_blocked");
    expect(initialJourneyStep([first, failed, later])).toBe(failed);
    expect(initialJourneyStep([first])).toBe(first);
    const assertion = step(2, "completed", JSON.stringify({ assertion_id: "heading", oracle: "visible_text",
      status: "not_satisfied", expected_value: "Guide", observed_value: "Settings" }));
    expect(initialJourneyStep([first, assertion])).toBe(assertion);
    expect(initialJourneyStep([])).toBeUndefined();
  });
  it("keeps deterministic cases distinct from personas and never invents an authentication request", () => {
    const journey = { persona_name: "Feature tester", result: { mode: "deep_feature_v1", case_id: "navigation" },
      execution_status: "failed", error_message: "absent_scope" } as unknown as JourneyExecution;
    expect(journeyIdentity(journey)).toEqual({ featureCase: true, caseId: "navigation", executor: "Deterministic browser executor" });
    expect(journeyBlocker(journey)).toContain("required page region was not found");
    expect(journeyBlocker(journey)).not.toMatch(/login|authentication/i);
    expect(journeyBlocker({ ...journey, error_message: "BrowserActionError",
      result: { diagnostic: { reason_code: "absent_scope" } } })).toContain("required page region was not found");
    expect(journeyIdentity({ ...journey, persona_name: "Researcher", result: null }).executor).toBe("Researcher");
    expect(journeyIdentity({ ...journey, result: null }).featureCase).toBe(false);
    expect(journeyIdentity({ ...journey, result: null }, true).featureCase).toBe(true);
  });
  it("distinguishes a required new scope approval from login assistance", () => {
    const journey = { execution_status: "policy_blocked", result: { diagnostic: {
      reason_code: "origin_not_authorized", requested_origin: "https://console.example.test",
    } } } as unknown as JourneyExecution;
    const text = journeyBlocker(journey);
    expect(text).toContain("https://console.example.test");
    expect(text).toContain("new exact-origin scope revision");
    expect(text).toContain("Logging in does not authorize");
  });
});


it("presents skipped human assistance as not tested instead of execution failure", () => {
  const journey = { execution_status: "skipped", result: null } as unknown as JourneyExecution;
  expect(journeyBlocker(journey)).toContain("Not tested—human assistance skipped");
  expect(journeyBlocker(journey)).not.toContain("failure");
});


it.each(["human_auth_bootstrap_v1", "browser_discovery_v1", null])("keeps %s discovery separate from feature cases", (runtime_name) => {
  const journey = { ordinal: 10000, runtime_name, persona_name: "Human authentication",
    result: null } as unknown as JourneyExecution;
  expect(journeyIdentity(journey, true)).toEqual({ discovery: true, featureCase: false,
    caseId: null, executor: "Browser discovery" });
});

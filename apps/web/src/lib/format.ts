import type { TestRun } from "./api";

export function textValue(value: unknown, fallback = "—"): string {
  if (typeof value === "string" && value.trim().length > 0) return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  return fallback;
}

/**
 * Return the user-facing Test name stored in the legacy `study_brief` snapshot field.
 *
 * `/runs` and `study_brief` remain compatibility identifiers in V1, but the product
 * language shown to users is consistently "Test".
 */
export function testBrief(configuration: Record<string, unknown>): string {
  return textValue(configuration.study_brief, "Untitled test");
}

export function testReference(run: TestRun): string {
  return typeof run.test_number === "number" && run.test_number > 0
    ? `MT-${String(run.test_number).padStart(6, "0")}`
    : run.id.slice(0, 8);
}

export function testTitle(run: TestRun): string {
  return `${testReference(run)} · ${textValue(run.configuration_snapshot.test_name, "Test")}`;
}

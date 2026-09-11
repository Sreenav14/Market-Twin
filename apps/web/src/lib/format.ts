export function textValue(value: unknown, fallback = "—"): string {
  if (typeof value === "string" && value.trim().length > 0) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
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

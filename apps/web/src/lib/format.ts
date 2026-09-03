export function textValue(value: unknown, fallback = "—"): string {
  if (typeof value === "string" && value.trim().length > 0) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

export function studyBrief(configuration: Record<string, unknown>): string {
  return textValue(configuration.study_brief, "Untitled study");
}

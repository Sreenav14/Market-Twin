export function vocabularyWord(words: Record<string, string>, value: unknown, fallback: string, development = import.meta.env.DEV) {
  if (typeof value !== "string" || !value.trim()) return fallback;
  if (Object.hasOwn(words, value)) return words[value];
  console.warn("Unmapped report vocabulary", value);
  return development ? value.toLowerCase().replace(/[_-]+/g, " ") : fallback;
}

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { HARNESS_ITEM_STATUS } from "../../lib/status";
import { observationReasons } from "./ContractReport";
import { assertionWords } from "./HarnessReport";
import { IMPRESSION_WORDS, PERSONA_TASK_WORDS } from "./PersonaImpressions";
import { VERDICT_WORDS } from "./ReportFrame";
import { ruleNames } from "./SlopReport";
import manifest from "./report-vocabulary-manifest.json";
import { vocabularyWord } from "./reportVocabulary";

const vocabularies = [
  [ruleNames, manifest.rules],
  [IMPRESSION_WORDS, manifest.impressions],
  [PERSONA_TASK_WORDS, manifest.personaTask],
  [VERDICT_WORDS.harness, manifest.harnessVerdicts],
  [VERDICT_WORDS.shipping, manifest.shippingVerdicts],
  [VERDICT_WORDS.contract, manifest.contractVerdicts],
  [HARNESS_ITEM_STATUS, manifest.boardOutcomes],
  [observationReasons, manifest.contractUnverified],
  [assertionWords, manifest.assertions],
] as const;

describe("Results vocabulary", () => {
  it("matches each display vocabulary to its producer manifest", () => {
    for (const [words, keys] of vocabularies) {
      expect(Object.keys(words).sort()).toEqual([...keys].sort());
      for (const key of keys) {
        const value = (words as Record<string, unknown>)[key];
        expect(typeof (Array.isArray(value) ? value[0] : value === null ? null :
          typeof value === "object" ? (value as { word?: string }).word : value)).toBe("string");
      }
    }
  });

  it("humanises unknown keys in development and uses neutral copy in production", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      expect(vocabularyWord(IMPRESSION_WORDS, "new_impression", "Observation", true)).toBe("new impression");
      expect(vocabularyWord(IMPRESSION_WORDS, "new_impression", "Observation", false)).toBe("Observation");
      expect(warn).toHaveBeenCalledWith("Unmapped report vocabulary", "new_impression");
    } finally {
      warn.mockRestore();
    }
  });

  it("covers all 42 producible catalogue rules and excludes producer-less rules", () => {
    const cataloguePath = resolve(process.cwd(), "../../packages/shared-python/src/markettwin_shared/slop_catalogue.json");
    const catalogue = JSON.parse(readFileSync(cataloguePath, "utf8")) as {
      rules: { id: string; severity: string | null }[];
    };
    const rules = catalogue.rules.filter(rule => (rule.id.startsWith("SLOP_") && rule.severity) || rule.id.startsWith("DEF_JS_"));
    expect(rules).toHaveLength(42);
    expect(rules.map(rule => rule.id).sort()).toEqual(manifest.rules);
  });

  it("uses reader-facing words for the focus signal and scopes ready with issues to Contract", () => {
    expect(IMPRESSION_WORDS.focus_indicator_invisible).toBe("Focus not visible");
    expect(VERDICT_WORDS.contract.ready_with_issues[0]).toBe("Ready, with issues");
    expect(VERDICT_WORDS.harness).not.toHaveProperty("ready_with_issues");
    expect(VERDICT_WORDS.shipping).not.toHaveProperty("ready_with_issues");
  });
});

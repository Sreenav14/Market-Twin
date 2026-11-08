import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Phase 2a (Soft Proof) token contract: the theme lives in the token
// layer, so these assertions pin the token VALUES and the retirements.
// They read the shipped CSS, not a copy of it.
const here = dirname(fileURLToPath(import.meta.url));
const cssFiles = readdirSync(here).filter((f) => f.endsWith(".css"));
const read = (name: string) => readFileSync(join(here, name), "utf8");
const allCss = cssFiles.map(read).join("\n");
const conceptTokens = read("concept-tokens.css");
const tokens = read("tokens.css");

const RETIRED = ["#FAF7F1", "#E4572E", "#BC4218", "#E4E0D6", "#E4E0F5", "#A83A15", "#1F7A3D", "#C62F3B", "#8A5F00"];

describe("Soft Proof token contract", () => {
  it("carries the Soft Proof surface and ink values", () => {
    for (const hex of ["#F5F4F2", "#ECECE9", "#EFEDEA", "#E6E3DE", "#D6D1CB", "#1C1917", "#57534E", "#79716B"]) {
      expect(conceptTokens).toContain(hex);
    }
  });

  it("carries the petrol accent pair and tint", () => {
    expect(conceptTokens).toContain("--accent: #0E7490");
    expect(conceptTokens).toContain("--accent-deep: #155E75");
    expect(conceptTokens).toContain("--accent-tint: #E6F2F5");
  });

  it("recolours semantics without changing their token names", () => {
    expect(conceptTokens).toContain("--pass: #1A7F37");
    expect(conceptTokens).toContain("--fail: #CF222E");
    expect(conceptTokens).toContain("--warn: #B54708");
    expect(conceptTokens).toContain("--warn-bg: #FFFAEB");
    expect(conceptTokens).toContain("--info-c: #475467");
  });

  it("has no retired warm hex anywhere in the stylesheets", () => {
    for (const hex of RETIRED) {
      expect(allCss.toUpperCase()).not.toContain(hex);
    }
  });

  it("uses the Soft Proof radius scale", () => {
    expect(tokens).toContain("--mt-radius-sm: 8px");
    expect(tokens).toContain("--mt-radius-lg: 12px");
    expect(tokens).toContain("--mt-radius-xl: 16px");
  });

  it("makes Hanken the UI face and JetBrains the evidence face", () => {
    expect(tokens).toContain('"Hanken Grotesk"');
    expect(tokens).toContain('--font-mono: "JetBrains Mono"');
  });

  it("keeps Newsreader out of the display role and inside quotes only", () => {
    const display = conceptTokens.slice(conceptTokens.indexOf(".font-display {"), conceptTokens.indexOf(".font-h1-workspace"));
    expect(display).not.toContain("Newsreader");
    const quote = conceptTokens.slice(conceptTokens.indexOf(".font-quote {"), conceptTokens.indexOf(".font-stat-numeral"));
    expect(quote).toContain("Newsreader");
    expect(quote).toContain("italic");
  });

  it("defines the Okabe-Ito chart order", () => {
    const order = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9"];
    order.forEach((hex, i) => expect(conceptTokens).toContain(`--chart-${i + 1}: ${hex}`));
  });

  it("scopes stage tokens to the live-viewer stylesheet only", () => {
    for (const f of cssFiles) {
      if (f === "live-execution.css") continue;
      expect(read(f), f).not.toContain("--stage-bg");
    }
    expect(read("live-execution.css")).toContain("--stage-bg: #101214");
  });
});

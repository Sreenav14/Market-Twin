import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SlopReport } from "./SlopReport";

describe("SlopReport", () => {
  it("shows the three families separately and never a verdict", () => {
    render(
      <SlopReport
        payload={{
          run_kind: "slop",
          families: {
            slop: {
              headline: "5.8%",
              percentage: 5.8,
              judged: 112,
              severe: 2,
              minor: 9,
              clean: 101,
              cant_tell: 8,
              coverage: 0.9333,
              page_signals: [],
            },
            defects: {
              serious: 1,
              minor: 0,
              per_rule: [
                {
                  rule_id: "DEF_JS_UNCAUGHT",
                  name: "Uncaught JavaScript exception",
                  severity: "serious",
                  occurrences: 1,
                  pages: ["https://app.example/"],
                },
              ],
            },
            effort: { value: null, reason: "No performed tasks in this run." },
            states_visited: 3,
          },
          states: [
            {
              url: "https://app.example/",
              page_signals: [],
              js_errors: [
                {
                  rule_id: "DEF_JS_UNCAUGHT",
                  severity: "serious",
                  message: "Cannot read properties of null",
                  count: 2,
                },
              ],
            },
            { url: "https://app.example/about", page_signals: [], js_errors: [] },
          ],
        }}
      />,
    );
    expect(screen.getByText("JavaScript errors by page")).toBeTruthy();
    expect(screen.getByText("Cannot read properties of null")).toBeTruthy();
    expect(screen.getByText(/×2/)).toBeTruthy();
    expect(screen.queryByText("https://app.example/about")).toBeNull();
    expect(screen.getByText("5.8%")).toBeTruthy();
    expect(screen.getByText(/112 judged element/)).toBeTruthy();
    expect(screen.getByText(/1 serious · 0 minor/)).toBeTruthy();
    expect(screen.getByText(/No performed tasks/)).toBeTruthy();
    expect(screen.queryByText(/Not ready yet|Ready to ship/)).toBeNull();
  });
});

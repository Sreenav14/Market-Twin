import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api";

import { SlopReport, type SlopReportPayload } from "./SlopReport";

describe("SlopReport", () => {
  it.each([
    [1200, 0, "93.6% of discovered elements could be judged. The score requires at least 80%."],
    [1200, null, "93.6% of discovered elements could be judged. 18.3% of measured element area was inconclusive. The limit is 10%."],
    [1000, 0, "94% of discovered elements could be judged. The score requires at least 80%."],
  ])("composes the Card A gate from %i judged elements and score %s", (judged, percentage, expected) => {
    render(<SlopReport payload={{
      families: {
        states_visited: 0,
        slop: { headline: "Stored headline", percentage, coverage: .936, judged, clean: judged,
          severe: 0, minor: 0, cant_tell: 0, page_signals: [],
          undecided_weight: percentage === null ? .183 : .01, undecided_basis: "area" },
        defects: { serious: 0, minor: 0, per_rule: [] },
        effort: { value: null },
      },
    }} />);
    const card = screen.getByRole("heading", { name: "UI slop score" }).closest("article")!;
    expect(within(card).getByText(expected)).toBeVisible();
  });
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("counts pending addresses by path and filters exact variants", () => {
    const path = "https://example.test/research/bench";
    render(<SlopReport payload={{
      run_kind: "slop",
      families: {
        states_visited: 1,
        slop: { headline: "0%", percentage: 0, judged: 1, severe: 0, minor: 0,
          clean: 1, cant_tell: 0, coverage: 1, page_signals: [] },
        defects: { serious: 0, minor: 0, per_rule: [] },
        effort: { value: null, reason: "No performed tasks in this run." },
      },
      coverage: {
        desktop_scan: true,
        pages_pending: 3,
        pending_urls: [`${path}?q=one`, "https://example.test/en-US/research/other?q=two", "https://example.test/settings"],
      },
    }} />);
    expect(screen.getByText("3 pending URLs across 2 site sections")).toBeInTheDocument();
    expect(screen.getByText("0%")).toBeVisible();
    expect(screen.queryByText(/other\?q=two · Pending/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "/research, 2 pending URLs" }));
    expect(screen.getByText(/other\?q=two · Pending/)).toBeInTheDocument();
    expect(screen.queryByText("https://example.test/settings · Pending")).toBeNull();
  });

  it("groups historical media reviews and removes recorded test conditions from the legacy minor total", () => {
    const url = "https://example.test/bfcm";
    render(<SlopReport payload={{
      families: {
        states_visited: 1,
        slop: { headline: "Insufficient coverage", percentage: null, judged: 2, severe: 2, minor: 0,
          clean: 0, cant_tell: 0, coverage: 0.95, page_signals: [] },
        defects: { serious: 0, minor: 5, per_rule: [{
          rule_id: "DEF_JS_CONSOLE_ERROR", name: "Browser console error", severity: "minor", occurrences: 5, pages: [url],
        }] },
        effort: { value: null },
      },
      states: [{ url, page_signals: [], elements: ["a.jpg", "b.jpg"].map(label => ({
        element_id: label, label, verdict: "slop", component: { role: "img", region: "main" },
        evidence: { response_status: 200 }, rules_fired: [{ rule_id: "SLOP_BROKEN_MEDIA", severity: "severe" }],
      })), js_errors: [{
        rule_id: "DEF_JS_CONSOLE_ERROR", severity: "minor", message: "Failed to load resource: net::ERR_EMPTY_RESPONSE", count: 3,
      }] }],
    }} />);
    expect(screen.getByRole("heading", { name: "2 images could not be verified on /bfcm" })).toBeVisible();
    const defects = screen.getByRole("heading", { name: "JavaScript signals" }).closest("article")!;
    expect(defects).toHaveTextContent("0 serious · 2 minor");
    expect(defects).toHaveTextContent("Browser console error · Minor · 2 occurrences · 0 pages");
    expect(screen.getByText("The server returned an empty response · 3 occurrences · 1 page")).toBeVisible();
    expect(screen.getByText(/severe flag count includes 2 image observations/)).toBeVisible();
    expect(screen.queryByText("a.jpg")).toBeNull();
  });

  it("shows the three families separately and opens saved evidence for a specific state", async () => {
    const access = vi.spyOn(api, "getArtifactAccess").mockResolvedValue({
      url: "https://evidence.test/signed-image", content_type: "image/png", artifact_type: "screenshot",
    } as Awaited<ReturnType<typeof api.getArtifactAccess>>);
    render(
      <SlopReport
        runId="audit-run"
        payload={{
          run_kind: "slop",
          coverage: { pages_pending: 34, paths_activated: 5, paths_not_assessed: 1,
            interaction_coverage: [{ url: "https://app.example/", viewport: "mobile320",
              path: "Menu", result: "approval_required" }] },
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
              page_signals: [{ rule_id: "UI_VISUAL_REVIEW", severity: "review", detail: "Menu overlap candidate" }],
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
              viewport: "mobile320", interaction_path: "Menu", screenshot_artifact_id: "saved-shot",
              measurement_evidence: { client_width: 320, scroll_width: 345 },
              elements: [{ element_id: "e1", label: "Start", verdict: "slop_minor",
                rules_fired: [{ rule_id: "SLOP_CONTRAST", severity: "minor" }],
                evidence: { contrast_ratio: 2.5, color: "rgb(160, 160, 160)" } }],
              page_signals: [{ rule_id: "AUDIT_PARTIAL_COVERAGE", severity: "info", detail: "34 pages pending" }],
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
    expect(screen.queryByText(/Cannot read properties of null/)).toBeNull();
    fireEvent.click(screen.getByText("Uncaught JavaScript exception · 2 occurrences · 1 page"));
    expect(await screen.findByText("Cannot read properties of null")).toBeVisible();
    expect(screen.getByText("https://app.example/about")).toBeVisible();
    expect(screen.getByText("5.8%")).toBeVisible();
    expect(screen.getByText("34 pending URLs")).toBeVisible();
    fireEvent.click(screen.getByText("Coverage details"));
    expect(await screen.findByText("Controls and UI states considered")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Design observations — unconfirmed" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Partial audit/ })).toBeVisible();
    expect(screen.getAllByText(/112 judged element/).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "JavaScript signals" }).closest("article")).toHaveTextContent("1 serious · 0 minor");
    expect(screen.getByText(/No performed tasks/)).toBeTruthy();
    expect(screen.queryByText(/Not ready yet|Ready to ship/)).toBeNull();
    expect(screen.getByRole("heading", { name: /Text contrast is below/ })).toBeInTheDocument();
    expect(access).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("link", { name: "https://app.example/" }));
    fireEvent.click(screen.getByRole("button", { name: "View evidence" }));
    expect(await screen.findByRole("img", { name: "Recorded screenshot evidence" })).toHaveAttribute("src", "https://evidence.test/signed-image");
    expect(access).toHaveBeenCalledWith("audit-run", "saved-shot");
    fireEvent.click(screen.getByRole("link", { name: "https://app.example/about" }));
    expect(screen.getByText("Screenshot evidence unavailable for this state.")).toBeInTheDocument();
    access.mockRestore();
  });

  it("ranks measured issues together and opens the relevant proof in every affected state", async () => {
    const access = vi.spyOn(api, "getArtifactAccess").mockImplementation(async (_runId, artifactId) => ({
      url: `https://evidence.test/${artifactId}`, content_type: "image/png", artifact_type: "screenshot",
    } as Awaited<ReturnType<typeof api.getArtifactAccess>>));
    const clipped = {
      element_id: "primary",
      label: "Open settings",
      verdict: "slop",
      rules_fired: [{ rule_id: "SLOP_CLIPPED_CONTROL_LABEL", severity: "severe" }],
      evidence: { label_clipped_horizontal_px: 18 },
    };
    const states: NonNullable<SlopReportPayload["states"]> = [
      {
        url: "https://app.example/account",
        viewport: "desktop1280",
        screenshot_artifact_id: "account-proof",
        measurement_evidence: { client_width: 1280, scroll_width: 1512 },
        elements: [clipped],
        page_signals: [
          { rule_id: "SLOP_VIEWPORT_INTEGRITY", severity: "severe", detail: "Page overflows horizontally." },
          { rule_id: "SLOP_DEAD_END", severity: "severe", detail: "Few controls were recorded." },
          { rule_id: "SLOP_DEFAULT_FONT", severity: "info", detail: "The same font is used for headings and body." },
        ],
        js_errors: [],
      },
      {
        url: "https://app.example/preferences",
        viewport: "desktop1280",
        screenshot_artifact_id: "preferences-proof",
        elements: [clipped],
        page_signals: [
          {
            rule_id: "UI_CONFIRMED_CONTROL_MISMATCH",
            severity: "severe",
            detail: "The same control has conflicting visibility across pages.",
            evidence_artifact_ids: ["account-proof", "preferences-proof"],
          },
          {
            rule_id: "UI_COMPONENT_VARIANT_REVIEW",
            severity: "review",
            detail: "Buttons may have genuinely different roles.",
            evidence_artifact_ids: ["account-proof", "preferences-proof"],
          },
        ],
        js_errors: [],
      },
    ];
    render(<SlopReport runId="audit-run" payload={{
      coverage: {
        desktop_scan: true, partial: true, pages_pending: 4, visual_reviews_unfinished: 1,
        lane_count: 4,
        retired_lanes: [{ lane_id: 3, cause: "browser_session" }],
        stop_reason: "Lead review unavailable.",
        desktop_budget: {
          stop_reason: "The desktop scan reached its time budget before all work finished.",
          human_wait_seconds: 12,
        },
      },
      families: {
        slop: {
          headline: "2%", percentage: 2, judged: 100, severe: 2, minor: 0, clean: 98, cant_tell: 0,
          coverage: 1, page_signals: states.flatMap(state => state.page_signals),
        },
        defects: { serious: 0, minor: 0, per_rule: [] },
        effort: { value: null },
        states_visited: 2,
      },
      states,
    }} />);
    const priorities = screen.getByRole("heading", { name: "What to check first" }).closest("section")!;
    expect(screen.getByText("1 of 4 browser lane retired during the scan.")).toBeVisible();
    fireEvent.click(screen.getByText("Coverage details"));
    expect(await screen.findByText("Lead review unavailable.")).toBeVisible();
    expect(screen.getByText(/The desktop scan reached its time budget/)).toBeVisible();
    expect(screen.getByText("Waited 12 seconds for a person to act")).toBeVisible();
    expect(screen.getByText("Visual review unfinished — 1 pages")).toBeVisible();
    const headings = within(priorities).getAllByRole("heading", { level: 4 });
    expect(headings.map(heading => heading.textContent)).toEqual([
      "Primary action text is clipped", "The same control has conflicting visibility across pages.",
      "Page content overflows the viewport",
    ]);
    const firstFinding = within(headings[0].closest("article")!);
    fireEvent.click(firstFinding.getByText("Affected pages"));
    const elementProof = await firstFinding.findByRole("link", { name: /preferences/ });
    fireEvent.click(elementProof);
    expect(document.getElementById("ui-element-1-primary")).toHaveFocus();
    expect(screen.getByText("Action text clipped by 18 px")).toBeVisible();
    fireEvent.click(within(headings[2].closest("article")!).getByRole("link"));
    expect(document.getElementById("ui-measurements-0")).toHaveFocus();
    expect(screen.getByText("Page scrolls sideways by 232 px")).toBeVisible();
    expect(access).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText(/Page has little content and no controls · 1 observation/));
    const loadCheck = await screen.findByText(/Check whether the page finished loading/);
    expect(within(loadCheck).getByRole("link")).toHaveAttribute("href", "#ui-state-0");
    expect(screen.getByText("1 supported cross-page mismatch")).toBeVisible();
    const comparison = within(headings[1].closest("article")!).getByRole("link", { name: "See comparison evidence" });
    expect(comparison).toHaveAttribute("href", "#ui-comparison-1-0");
    fireEvent.click(comparison);
    const panel = screen.getByRole("region", { name: "Recorded evidence" });
    expect(panel).toHaveFocus();
    const captures = within(panel).getAllByRole("figure");
    expect(captures.map(capture => capture.textContent)).toEqual([
      expect.stringContaining("https://app.example/account · Desktop"),
      expect.stringContaining("https://app.example/preferences · Desktop"),
    ]);
    expect(await within(captures[0]).findByRole("img")).toHaveAttribute("src", "https://evidence.test/account-proof");
    expect(await within(captures[1]).findByRole("img")).toHaveAttribute("src", "https://evidence.test/preferences-proof");
    expect(access).toHaveBeenCalledTimes(2);
    fireEvent.click(within(panel).getByRole("button", { name: "Back to audit summary" }));
    expect(comparison).toHaveFocus();
    const observations = screen.getByRole("heading", { name: "Design observations — unconfirmed" }).closest("section")!;
    fireEvent.click(within(observations).getByText(/Default font/));
    fireEvent.click(within(observations).getByText(/Component variants/));
    expect(await within(observations).findByText(/same font/)).toBeVisible();
    expect(await within(observations).findByText(/genuinely different roles/)).toBeVisible();
    access.mockRestore();
  });

  it("opens a saved element fragment beyond the initial inventory and suppresses an ineligible score", () => {
    window.history.replaceState(null, "", "#ui-element-58-e161");
    const states = Array.from({ length: 60 }, (_, index) => ({
      url: `https://example.test/article/${index}`, page_signals: [], js_errors: [],
      elements: index === 58 ? [{
        element_id: "e161", label: "acme_support_kb", verdict: "slop",
        evidence: { contrast_ratio: 4.4736, x: 30, y: 4550, width: 75, height: 20 },
        rules_fired: [{ rule_id: "SLOP_PLACEHOLDER_TEXT", severity: "severe" }, { rule_id: "SLOP_CONTRAST", severity: "minor" }],
      }] : [],
    }));
    render(<SlopReport payload={{
      families: {
        states_visited: states.length,
        slop: { headline: "Insufficient coverage", percentage: null, judged: 1, severe: 1,
          minor: 0, clean: 0, cant_tell: 2, coverage: .3333, page_signals: [] },
        defects: { serious: 0, minor: 0, per_rule: [] }, effort: { value: null },
      },
      states,
    }} />);
    const evidence = screen.getByRole("region", { name: "Recorded evidence" });
    expect(evidence).toHaveFocus();
    expect(within(evidence).getByText("Text: “acme_support_kb”")).toBeVisible();
    expect(within(evidence).getByText("Contrast 4.4736:1")).toBeVisible();
    expect(within(evidence).getByText(/Needs review — this can be intentional/)).toBeVisible();
    expect(within(evidence).getByText(/No screenshot covers this element/)).toBeVisible();
    const priorities = screen.getByRole("region", { name: "What to check first" });
    expect(within(priorities).getAllByRole("heading", { level: 4 }).map(heading => heading.textContent)).toEqual([
      "Text contrast is below the measured threshold", "Possible placeholder text",
    ]);
    expect(screen.getByText("Insufficient coverage")).toBeVisible();
    expect(screen.getByText("33% of discovered elements could be judged. The score requires at least 80% coverage.")).toBeVisible();
    expect(screen.queryByText(/^\d+(?:\.\d+)?%$/)).toBeNull();
    const inventory = screen.getByRole("region", { name: "State inventory" });
    expect(within(inventory).getAllByRole("listitem")).toHaveLength(20);
    fireEvent.click(within(evidence).getByRole("button", { name: "Back to audit summary" }));
    expect(screen.queryByRole("region", { name: "Recorded evidence" })).toBeNull();
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  fetchAppMapSkillUsage,
  fetchAppMapSkills,
  request,
  type AppMapSkillLibraryLine,
} from "../../lib/api";
import { AppMapPanel, type AppMapSummary } from "./AppMapPanel";

vi.mock("../../lib/api", () => ({ request: vi.fn(), fetchAppMapSkills: vi.fn(async () => ({ items: [] })), fetchAppMapSkillUsage: vi.fn() }));

const mockedRequest = vi.mocked(request);
const base = "/api/v1/workspaces/ws/applications/app/targets/target";

const summary: AppMapSummary = {
  map_id: "map-1",
  version_number: 2,
  status: "ready",
  release_state: "partial",
  release_scope: "harvest",
  base_url: "https://example.com/",
  builder_version: "census-1a.1",
  started_at: "2026-11-14T10:00:00Z",
  completed_at: "2026-11-14T10:25:00Z",
  counts: { expected: 4650, reachable: 4650, by_status: { fetch_ok: 4631, redirect: 19 } },
  gate_metrics: {},
  spend: { calls: 0, tokens: 0, seconds: 1459.3 },
  harvest: {
    status: "ready",
    visited: 4600,
    reachable: 4650,
    blocked: 20,
    failed: 5,
    unprobed_budget: 25,
    enriched_groups: 12,
    template_groups: 14,
    spend: { calls: 40, tokens: 210000 },
  },
  freshness: {
    state: "current",
    last_preflight_at: "2026-11-14T12:30:00Z",
    last_preflight_id: "pf-1",
    outcome_counts: {
      present: 4650,
      changed: 0,
      unreachable: 0,
      missing: 0,
      new: 0,
    },
    deferred_count: 0,
  },
  skills: [
    {
      name: "reach-get-a-demo",
      lifecycle_status: "active",
      last_replay_result: "passed",
      last_replay_at: "2026-11-14T11:00:00Z",
    },
  ],
};

function renderPanel() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AppMapPanel workspaceId="ws" applicationId="app" targetId="target" />
    </QueryClientProvider>,
  );
}

describe("AppMapPanel (T-W1)", () => {
  it("renders the map summary: release chip, census counts, harvest coverage, and enrichment spend", async () => {
    mockedRequest.mockImplementation(async (url) => {
      const base = "/api/v1/workspaces/ws/applications/app/targets/target";
      if (url === `${base}/app-map`) return summary;
      if (url === `${base}/app-map/audits/latest`) return null;
      if (url === `${base}/app-map/skills`) return { items: [] };
      if (url === `${base}/app-maps/map-1/expectations`) return { items: [], gate: {} };
      if (url === `${base}/app-maps/map-1/expectations/suggestions`) return { items: [] };
      if (url === `${base}/app-maps/map-1/conflicts`) return { items: [] };
      throw new Error(`Unexpected request: ${url}`);
    });
    renderPanel();
    expect(await screen.findByText("Map v2")).toBeInTheDocument();
    await waitFor(() => expect(mockedRequest).toHaveBeenCalledWith(
      "/api/v1/workspaces/ws/applications/app/targets/target/app-map/audits/latest",
    ));
    expect(screen.getByText(/partial/)).toBeInTheDocument();
    expect(screen.getByText(/4650 reachable of 4650 expected/)).toBeInTheDocument();
    expect(
      screen.getByText(/4600 visited of 4650 reachable/),
    ).toBeInTheDocument();
    expect(screen.getByText(/20 blocked/)).toBeInTheDocument();
    expect(screen.getByText(/25 unprobed \(budget\)/)).toBeInTheDocument();
    expect(
      screen.getByText(/12 of 14 template groups enriched/),
    ).toBeInTheDocument();
    expect(screen.getByText(/40 model calls/)).toBeInTheDocument();
    // The summary's old skill line is deleted: skills render once, in
    // the Skill library section (empty here — its fetch has no items).
    expect(screen.queryByText("reach-get-a-demo")).not.toBeInTheDocument();
    expect(await screen.findByText(/No skills yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Harvest" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Build app map" })).toBeEnabled();
  });

  it("shows the exact empty state and a Build button when no map exists", async () => {
    mockedRequest.mockRejectedValue(Object.assign(new Error("no app map"), { status: 404 }));
    renderPanel();
    expect(
      await screen.findByText(
        "No application map yet — the map is built from the live site, in code, with no model calls",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Build app map" })).toBeInTheDocument();
  });

  it("shows a retryable error instead of claiming the map is absent", async () => {
    mockedRequest.mockRejectedValue(Object.assign(new Error("unavailable"), { status: 503 }));
    renderPanel();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the application map");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Build app map" })).not.toBeInTheDocument();
  });

  it("starts ingestion through the exact build endpoint and shows the resulting map", async () => {
    let built = false;
    mockedRequest.mockImplementation(async (url, init) => {
      if (url === `${base}/map-builds` && init?.method === "POST") {
        built = true;
        return { map_id: "map-1", version_number: 2, status: "building" };
      }
      if (url === `${base}/app-map`) {
        if (!built) throw Object.assign(new Error("no app map"), { status: 404 });
        return summary;
      }
      if (url === `${base}/app-map/audits/latest`) return null;
      if (url === `${base}/app-maps/map-1/expectations`) return { items: [], gate: {} };
      if (url === `${base}/app-maps/map-1/expectations/suggestions`) return { items: [] };
      if (url === `${base}/app-maps/map-1/conflicts`) return { items: [] };
      throw new Error(`Unexpected request: ${url}`);
    });
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: "Build app map" }));
    await waitFor(() => expect(mockedRequest).toHaveBeenCalledWith(
      `${base}/map-builds`, { method: "POST" },
    ));
    expect(await screen.findByText("Map v2")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Knowledge build requested");
  });

  it("shows ingestion failures so the button does not silently fail", async () => {
    mockedRequest.mockImplementation(async (url) => {
      if (url === `${base}/app-map`) {
        throw Object.assign(new Error("no app map"), { status: 404 });
      }
      throw new Error("build unavailable");
    });
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: "Build app map" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not start knowledge ingestion");
    expect(screen.getByRole("button", { name: "Build app map" })).toBeEnabled();
  });
});

describe("AppMapPanel Phase 2 sections (T-PN)", () => {
  it("keeps failed sections distinct from empty knowledge", async () => {
    mockedRequest.mockImplementation(async (url) => {
      if (url === `${base}/app-map`) return summary;
      throw new Error("unavailable");
    });
    vi.mocked(fetchAppMapSkills).mockRejectedValueOnce(new Error("unavailable"));
    renderPanel();
    expect(await screen.findByRole("button", { name: "Retry expectations" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Retry skills" })).toBeInTheDocument();
    expect(screen.queryByText(/No expectations yet/)).not.toBeInTheDocument();
  });

  function mockPhase2() {
    mockedRequest.mockImplementation((url: string) => {
      if (url === `${base}/app-map`) return Promise.resolve(summary);
      if (url === `${base}/app-maps/map-1/expectations`)
        return Promise.resolve({
          items: [
            {
              id: "exp-1",
              statement: "Clicking 'Buy now' navigates to /checkout",
              oracle_source: "documentation",
              status: "owner-confirmed",
              verdict_eligible: true,
              assertion_kind: "navigation",
            },
          ],
          gate: { expectation_gate: { release_scope: "expectations" } },
        });
      if (url === `${base}/app-maps/map-1/expectations/suggestions`)
        return Promise.resolve({
          items: [
            {
              id: "exp-2",
              statement: "'Buy now' is present and visible",
              oracle_source: "observation",
              status: "unverified",
              verdict_eligible: false,
              assertion_kind: "element_state",
            },
          ],
        });
      if (url === `${base}/app-maps/map-1/conflicts`)
        return Promise.resolve({
          items: [
            {
              id: "conf-1",
              expectation_id: "exp-1",
              conflict_kind: "navigation_mismatch",
              detection_source: "grounding",
              observed_behaviour: "Clicking 'Buy now' navigates to /cart",
              status: "open",
            },
          ],
        });
      if (url === `${base}/app-map/audits/latest`)
        return Promise.resolve({
          audit_kind: "scheduled",
          checks: {},
          findings: [{ check: "A2" }, { check: "A5" }],
          created_at: "2026-11-14T12:00:00Z",
        });
      return Promise.resolve({});
    });
  }

  it("renders expectations, suggestions, conflicts and the audit line", async () => {
    mockPhase2();
    renderPanel();
    expect(await screen.findByRole("heading", { name: "Expectations" })).toBeInTheDocument();
    expect(
      await screen.findByText("Clicking 'Buy now' navigates to /checkout"),
    ).toBeInTheDocument();
    expect(screen.getByText(/gate scope: expectations/)).toBeInTheDocument();
    expect(await screen.findByText("Suggestions")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(await screen.findByText("Conflicts")).toBeInTheDocument();
    expect(
      screen.getByText("Clicking 'Buy now' navigates to /cart"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Docs win" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "App wins" })).toBeInTheDocument();
    expect(await screen.findByText(/Latest audit: scheduled/)).toBeInTheDocument();
    expect(screen.getByText(/2 findings/)).toBeInTheDocument();
  });

  it("approving a suggestion posts to the per-record promote endpoint", async () => {
    mockPhase2();
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
    await waitFor(() =>
      expect(
        mockedRequest.mock.calls.some(([url]) =>
          url === `${base}/app-maps/map-1/expectations/exp-2/promote`,
        ),
      ).toBe(true),
    );
  });

  it("offers the grounding trigger with the probe toggle", async () => {
    mockPhase2();
    renderPanel();
    expect(
      await screen.findByRole("button", { name: "Ground expectations" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Probe form validation/)).toBeInTheDocument();
    expect(
      screen.getByText(/probe step is skipped and named/),
    ).toBeInTheDocument();
  });
});

describe("AppMapPanel freshness (T-W3)", () => {
  it("renders the freshness state, last preflight time, and outcome counts", async () => {
    mockedRequest.mockResolvedValue({
      ...summary,
      freshness: {
        state: "stale",
        last_preflight_at: "2026-11-14T12:30:00Z",
        last_preflight_id: "pf-1",
        outcome_counts: {
          present: 4640,
          changed: 4,
          unreachable: 3,
          missing: 2,
          new: 1,
        },
        deferred_count: 0,
      },
    });
    renderPanel();
    expect(await screen.findByRole("link", { name: "Freshness" })).toHaveAttribute("href", "#app-map-freshness");
    expect(screen.getByText(/stale · last preflight/)).toBeInTheDocument();
    expect(screen.getByText(/4640 present/)).toBeInTheDocument();
    expect(screen.getByText(/4 changed/)).toBeInTheDocument();
    expect(screen.getByText(/3 unreachable/)).toBeInTheDocument();
    expect(screen.getByText(/2 missing/)).toBeInTheDocument();
    expect(screen.getByText(/1 new/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Check freshness" }),
    ).toBeEnabled();
  });

  it("renders an unchecked map as 'not checked yet', never as current", async () => {
    mockedRequest.mockResolvedValue({
      ...summary,
      freshness: {
        state: "unknown",
        last_preflight_at: null,
        last_preflight_id: null,
        outcome_counts: {
          present: 0,
          changed: 0,
          unreachable: 0,
          missing: 0,
          new: 0,
        },
        deferred_count: 0,
      },
    });
    renderPanel();
    const line = await screen.findByText("not checked yet");
    expect(line).toBeInTheDocument();
    expect(line.textContent).not.toContain("current");
  });
});
describe("AppMapPanel skill library (T-TS12)", () => {
  const line = (
    over: Partial<AppMapSkillLibraryLine>,
  ): AppMapSkillLibraryLine => ({
    skill_id: "skill-x",
    name: "skill",
    skill_kind: "journey",
    lifecycle_status: "draft",
    version_id: "version-1",
    version_number: 1,
    last_replay_result: null,
    last_replay_at: null,
    replay_count: 0,
    heal_count: 0,
    retired_reason: null,
    diagnosis_model_calls: 0,
    status_reason: null,
    ...over,
  });

  const library: AppMapSkillLibraryLine[] = [
    line({
      skill_id: "s-candidate",
      name: "candidate-task",
      skill_kind: "task",
      task_source_kind: "document",
    }),
    line({ skill_id: "s-draft-task", name: "draft-task", skill_kind: "task" }),
    line({ skill_id: "s-draft", name: "draft-journey" }),
    line({
      skill_id: "s-verified",
      name: "verified-journey",
      lifecycle_status: "replay_verified",
      replay_count: 2,
      last_replay_result: "passed",
      last_replay_at: "2026-11-14T11:00:00Z",
    }),
    line({
      skill_id: "s-active",
      name: "active-journey",
      lifecycle_status: "active",
      replay_count: 5,
      last_replay_result: "passed",
      last_replay_at: "2026-11-14T11:00:00Z",
    }),
    line({
      skill_id: "s-suspect",
      name: "suspect-journey",
      lifecycle_status: "suspect",
      status_reason: "locator_drift",
    }),
    line({
      skill_id: "s-quarantined",
      name: "quarantined-journey",
      lifecycle_status: "quarantined",
      status_reason: "assertion_divergence",
    }),
    line({
      skill_id: "s-retired",
      name: "retired-journey",
      lifecycle_status: "retired",
      retired_reason: "owner",
      status_reason: "owner",
    }),
  ];

  function mockLibrary() {
    mockedRequest.mockImplementation(async (url) => {
      if (url === `${base}/app-map`) return summary;
      if (url === `${base}/app-map/audits/latest`) return null;
      if (url === `${base}/app-maps/map-1/expectations`)
        return { items: [], gate: {} };
      if (url === `${base}/app-maps/map-1/expectations/suggestions`)
        return { items: [] };
      if (url === `${base}/app-maps/map-1/conflicts`) return { items: [] };
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.mocked(fetchAppMapSkills).mockResolvedValue({ items: library });
  }

  function group(name: string) {
    const container = screen.getByRole("heading", { name }).closest("div");
    if (!container) throw new Error(`group container missing for ${name}`);
    return within(container as HTMLElement);
  }

  it("renders the four groups in order, each lifecycle state under exactly one group", async () => {
    mockLibrary();
    renderPanel();
    expect(await screen.findByText("candidate-task")).toBeInTheDocument();
    expect(
      screen.getAllByRole("heading", { level: 5 }).map((h) => h.textContent),
    ).toEqual([
      "Source knowledge — not yet a skill",
      "Draft task skills",
      "Verified skills",
      "Skills requiring attention",
    ]);
    expect(
      group("Source knowledge — not yet a skill").getByText("candidate-task"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Source-derived skill — execution unverified"),
    ).toHaveLength(1);
    // A draft task skill without the document marker is a compiled
    // draft, not a candidate: it lands in Draft task skills.
    expect(group("Draft task skills").getByText("draft-task")).toBeInTheDocument();
    expect(group("Draft task skills").getByText("draft-journey")).toBeInTheDocument();
    expect(
      screen.getAllByText("Draft — compiled, not yet replay-verified"),
    ).toHaveLength(2);
    expect(group("Verified skills").getByText("verified-journey")).toBeInTheDocument();
    expect(group("Verified skills").getByText("active-journey")).toBeInTheDocument();
    expect(
      screen.getAllByText("Replay-verified — waiting for activation"),
    ).toHaveLength(1);
    expect(screen.getAllByText("Active — runs replay it in tests")).toHaveLength(1);
    expect(
      group("Skills requiring attention").getByText("suspect-journey"),
    ).toBeInTheDocument();
    expect(
      group("Skills requiring attention").getByText("quarantined-journey"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Suspect — a replay disagreed; re-checking"),
    ).toHaveLength(1);
    expect(screen.getAllByText("Quarantined — held out of runs")).toHaveLength(1);
  });

  it("keeps retired skills collapsed until asked", async () => {
    mockLibrary();
    renderPanel();
    expect(await screen.findByText("candidate-task")).toBeInTheDocument();
    expect(screen.queryByText("retired-journey")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retired (1)" }));
    expect(screen.getByText("retired-journey")).toBeInTheDocument();
    expect(screen.getByText("Retired — no longer used")).toBeInTheDocument();
  });

  it("expands a skill's usage history from the usage endpoint", async () => {
    mockLibrary();
    vi.mocked(fetchAppMapSkillUsage).mockReset();
    vi.mocked(fetchAppMapSkillUsage).mockResolvedValue({
      skill_id: "s-active",
      total_model_calls: 4,
      total_model_tokens: 1200,
      diagnosis_model_calls: 1,
      events_by_kind: { replay: 3, served: 2, heal_diagnosis: 1 },
      latest_version: {
        version_id: "version-9",
        version_number: 3,
        lifecycle_status: "active",
        replay_count: 5,
        heal_count: 1,
        last_replay_result: "passed",
        last_replay_at: "2026-11-14T11:00:00Z",
        retired_reason: null,
      },
    });
    renderPanel();
    const row = (await screen.findByText("active-journey")).closest("li");
    if (!row) throw new Error("active-journey row missing");
    fireEvent.click(
      within(row as HTMLElement).getByRole("button", { name: "History" }),
    );
    expect(await screen.findByText(/Usage history:/)).toBeInTheDocument();
    expect(fetchAppMapSkillUsage).toHaveBeenCalledWith(base, "s-active");
    expect(screen.getByText(/replay × 3/)).toBeInTheDocument();
    expect(screen.getByText(/served × 2/)).toBeInTheDocument();
    expect(screen.getByText(/Latest version v3/)).toBeInTheDocument();
    expect(screen.getByText(/4 model calls · 1200 tokens/)).toBeInTheDocument();
  });

  it("shows a retryable error when the usage fetch fails, not an empty history", async () => {
    mockLibrary();
    vi.mocked(fetchAppMapSkillUsage).mockReset();
    vi.mocked(fetchAppMapSkillUsage).mockRejectedValue(new Error("unavailable"));
    renderPanel();
    const row = (await screen.findByText("active-journey")).closest("li");
    if (!row) throw new Error("active-journey row missing");
    fireEvent.click(
      within(row as HTMLElement).getByRole("button", { name: "History" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load this skill's usage",
    );
    expect(
      screen.getByRole("button", { name: "Retry usage" }),
    ).toBeInTheDocument();
  });
});

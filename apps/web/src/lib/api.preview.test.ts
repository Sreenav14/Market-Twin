import { afterEach, expect, it, vi } from "vitest";

import { api } from "./api";

afterEach(() => vi.unstubAllGlobals());

it("follows bounded run pages without truncating aggregate counts", async () => {
  const page = Array.from({ length: 100 }, (_, index) => ({ id: `run-${index}` }));
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(page)))
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: "run-100" }])));
  vi.stubGlobal("fetch", fetchMock);
  expect(await api.listRuns("app")).toHaveLength(101);
  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
    "/api/v1/applications/app/test-runs?limit=100&offset=0",
    "/api/v1/applications/app/test-runs?limit=100&offset=100",
  ]);
});

it("marks JSON mutations for the shared browser origin policy", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.logout();
  expect(fetchMock.mock.calls[0][1].headers).toMatchObject({ "X-MarketTwin-Request": "1" });
});

it("starts ordinary runs with runtime assistance and no upfront identity policy", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "run" }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.createRun("app", "target", "Test the protected page");
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  const payload = JSON.parse(init.body as string);
  expect(payload.run_kind).toBe("explore_test");
  expect(payload).not.toHaveProperty("execution_mode");
  expect(payload.runtime_human_assistance).toBe(true);
  expect(payload).not.toHaveProperty("auth_verification");
  expect(payload).not.toHaveProperty("auth_mode");
});

it.each(["explore_test", "persona", "slop"])(
  "preserves the selected %s run kind in the HTTP request",
  async (mode) => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "run" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.createRun("app", "target", "Test the fixture", "medium", "", mode);

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/applications/app/test-runs");
    expect(JSON.parse(init.body as string).run_kind).toBe(mode);
  },
);

it("sends a distinct authenticated skip request without browser secrets", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "request", status: "skipped" }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await expect(api.skipHumanAction("request")).resolves.toEqual({ id: "request", status: "skipped" });
  const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(path).toBe("/api/v1/human-actions/request/skip");
  expect(init.method).toBe("POST");
  expect(init.credentials).toBe("include");
  expect(init.headers).toMatchObject({ "X-MarketTwin-Request": "1" });
  expect(init.body).toBeUndefined();
});

it("preserves explicit identity policies for existing API callers", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "run" }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const policy = { origin: "https://fixture.test", marker_selector: "#identity", expected_marker: "user", role: "user", account_reference: "synthetic-01" };
  await api.createRun("app", "target", "Verify protected fixture", "low", "", "persona", policy, false, false, [], "required", false);
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(JSON.parse(init.body as string)).toMatchObject({
    auth_verification: policy, auth_mode: "required", runtime_human_assistance: false,
  });
});

it("sends the run mode and approved test data only for standard runs (W1)", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "run" }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.createRun("app", "target", "Test the fixture", "medium", "", "explore_test", undefined, false, false, [], undefined, true, false, "standard", [{ key: "company_name", value: "Thread & Co. Test" }]);
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  const payload = JSON.parse(init.body as string);
  expect(payload.harness_run_mode).toBe("standard");
  expect(payload.approved_test_data).toEqual([{ key: "company_name", value: "Thread & Co. Test" }]);
});

it("omits the run mode for read-only runs (W1)", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "run" }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.createRun("app", "target", "Test the fixture");
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  const payload = JSON.parse(init.body as string);
  expect(payload).not.toHaveProperty("harness_run_mode");
  expect(payload).not.toHaveProperty("approved_test_data");
});

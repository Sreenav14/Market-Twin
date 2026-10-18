import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { RunContext } from "../../layouts/RunLayout";
import { api } from "../../lib/api";
import { HumanActionPage, HumanAssistanceHost } from "./HumanActionPage";

const counts = vi.hoisted(() => ({ mounted: 0, removed: 0 }));
vi.mock("./HumanBrowserViewer", () => ({ HumanBrowserViewer: () => {
  useEffect(() => { counts.mounted += 1; return () => { counts.removed += 1; }; }, []);
  return <div data-testid="protected-viewer">Protected viewer</div>;
} }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); counts.mounted = 0; counts.removed = 0; });

it("keeps one lease owner and the same viewer through live, legacy and other run routes", async () => {
  const user = userEvent.setup();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(api, "listHumanActions").mockResolvedValue([{
    id: "request", test_run_id: "run", execution_id: "execution", browser_session_id: "browser",
    request_type: "login", status: "pending", created_at: "2026-10-18T12:00:00Z", expires_at: null,
    control_generation: 0, lease_id: null, lease_expires_at: null,
  }]);
  vi.spyOn(api, "listActionApprovals").mockResolvedValue([]);
  const claim = vi.spyOn(api, "claimHumanAction").mockResolvedValue({ request_id: "request", browser_session_id: "browser", lease_id: "lease", lease_token: "secret-token", generation: 1, expires_at: "2026-10-18T12:30:00Z", viewer_available: true, viewer_url: "wss://fixture.test/viewer", viewer_ticket: "secret-ticket" });
  const release = vi.spyOn(api, "releaseHumanAction").mockResolvedValue({ generation: 2 });
  const context = { run: { id: "run", status: "awaiting_human" }, user: { id: "owner" }, workspace: { id: "workspace", role: "owner" } } as RunContext;
  function Layout() { return <HumanAssistanceHost context={context}>
    <nav><Link to="/runs/run/activity">Live route</Link><Link to="/runs/run/human-action">Legacy route</Link><Link to="/runs/run/overview">Summary route</Link></nav>
    <Outlet context={context} />
  </HumanAssistanceHost>; }
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/run/activity"]}><Routes>
    <Route path="/runs/run" element={<Layout />}><Route path="activity" element={<HumanActionPage />} /><Route path="human-action" element={<HumanActionPage />} /><Route path="overview" element={<h2>Summary</h2>} /></Route>
  </Routes></MemoryRouter></QueryClientProvider>);
  await user.click(await screen.findByRole("button", { name: /Take browser control/ }));
  const original = await screen.findByTestId("protected-viewer");
  await user.click(screen.getByRole("link", { name: "Legacy route" }));
  expect(screen.getByTestId("protected-viewer")).toBe(original);
  await user.click(screen.getByRole("link", { name: "Summary route" }));
  expect(screen.getByRole("heading", { name: "You still control the test browser" })).toBeVisible();
  expect(screen.getByTestId("protected-viewer")).toBeVisible();
  await user.click(screen.getByRole("link", { name: "Return to browser control" }));
  expect(screen.getByTestId("protected-viewer")).toBe(original);
  expect(counts.mounted).toBe(1);
  expect(counts.removed).toBe(0);
  expect(claim).toHaveBeenCalledOnce();
  await user.click(screen.getByRole("button", { name: "Done—resume agent" }));
  expect(release).toHaveBeenCalledOnce();
  expect(JSON.stringify(client.getMutationCache().getAll().map((item) => item.state))).not.toContain("secret-token");
});

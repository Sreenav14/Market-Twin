import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError, api, Application, Target, TargetAuthorization } from "../../lib/api";
import { ApplicationOverviewPage } from "./ApplicationOverviewPage";

const application: Application = { id: "app-1", workspace_id: "ws-1", created_by_user_id: "user-1", name: "Storefront", description: null, status: "active" };
const target: Target = { id: "target-1", application_id: "app-1", name: "Staging", environment: "staging", base_url: "https://staging.example.com", requires_auth: false, status: "active", allowed_origins: [] };
const authorization: TargetAuthorization = { id: "auth-1", target_id: "target-1", created_by_user_id: "user-1", authorized_by_user_id: "user-1", status: "authorized", authorization_basis: "Owned target", created_at: "2026-10-18", authorized_at: "2026-10-18", revoked_at: null, expires_at: null };

beforeEach(() => {
  vi.spyOn(api, "getApplication").mockResolvedValue(application);
  vi.spyOn(api, "listRuns").mockResolvedValue([]);
  vi.spyOn(api, "listTargets").mockResolvedValue([target]);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function open() {
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={["/applications/app-1"]}><Routes>
    <Route element={<Outlet context={{ workspace: { id: "ws-1", role: "owner" } }} />}>
      <Route path="/applications/:applicationId" element={<ApplicationOverviewPage />} />
    </Route>
  </Routes></MemoryRouter></QueryClientProvider>);
}

it("waits for target readiness before suggesting configuration or authorization", async () => {
  let resolve!: (targets: Target[]) => void;
  vi.mocked(api.listTargets).mockReturnValue(new Promise((done) => { resolve = done; }));
  vi.spyOn(api, "getAuthorization").mockResolvedValue(authorization);
  open();
  await screen.findByRole("heading", { name: "Storefront" });
  expect(screen.getByText(/Loading targets/)).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Add target|Authorize target|New test/ })).not.toBeInTheDocument();
  expect(screen.queryByText("Targets (0)")).not.toBeInTheDocument();
  await act(async () => { resolve([target]); });
  expect((await screen.findAllByRole("link", { name: /New test/ })).length).toBeGreaterThan(0);
});

it("keeps an authorization outage distinct from missing authorization and recovers on retry", async () => {
  vi.spyOn(api, "getAuthorization").mockRejectedValueOnce(new ApiError("Unavailable", 503)).mockResolvedValue(authorization);
  open();
  await screen.findByText("unavailable");
  expect(screen.queryByText("not authorized")).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Authorize target|New test/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry target readiness" }));
  await screen.findByText("authorized");
  expect(screen.queryByRole("button", { name: "Retry target readiness" })).not.toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /New test/ }).length).toBeGreaterThan(0);
});

it("offers retry after a target-list outage instead of suggesting an empty configuration", async () => {
  vi.mocked(api.listTargets).mockRejectedValue(new ApiError("Targets unavailable", 503));
  open();
  await screen.findByText("Targets unavailable");
  expect(screen.queryByRole("link", { name: /Add target|Authorize target/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry target readiness" })).toBeInTheDocument();
});

it("offers authorization when the API confirms that the grant is missing", async () => {
  vi.spyOn(api, "getAuthorization").mockRejectedValue(new ApiError("Not found", 404));
  open();
  await screen.findByText("not authorized");
  expect(screen.getAllByRole("link", { name: /Authorize target/ }).length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: "Retry target readiness" })).not.toBeInTheDocument();
});

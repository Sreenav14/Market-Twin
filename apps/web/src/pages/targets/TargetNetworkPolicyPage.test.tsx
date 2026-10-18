import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { TargetNetworkPolicyPage } from "./TargetNetworkPolicyPage";

const target = { id: "target-1", application_id: "app-1", name: "Original scope", environment: "test", base_url: "http://127.0.0.1:8765", requires_auth: false, status: "active", allowed_origins: [{ scheme: "http", hostname: "127.0.0.1", port: 8765, include_subdomains: false }] };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function open(role: string) {
  render(<MemoryRouter initialEntries={["/targets/target-1/network"]}><Routes>
    <Route element={<Outlet context={{ workspace: { id: "ws-1", role } }} />}>
      <Route path="/targets/:targetId/network" element={<TargetNetworkPolicyPage />} />
    </Route>
  </Routes></MemoryRouter>);
}
function response(value: unknown) {
  return Promise.resolve(new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } }));
}
it("shows exact origins and denies scope controls to members", async () => {
  vi.stubGlobal("fetch", vi.fn((url: string) => response(url.endsWith("scope-revisions") ? [] : target)));
  open("member");
  expect(await screen.findByText("Current scope: Original scope")).toBeInTheDocument();
  expect(screen.getByText("http://127.0.0.1:8765")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Create pending scope" })).not.toBeInTheDocument();
  expect(screen.getByText(/Only workspace owners and admins/)).toBeInTheDocument();
});
it("creates a pending scope only after explicit confirmation and shows authorization review", async () => {
  let requested: unknown;
  let created = false;
  const revision = { ...target, id: "target-2", name: "Console scope", scope_parent_id: target.id };
  const fetchMock = vi.fn((url: string, options?: RequestInit) => {
    if (options?.method === "POST") {
      requested = JSON.parse(String(options.body)); created = true;
      return response(revision);
    }
    return response(url.endsWith("scope-revisions") ? (created ? [revision] : []) : target);
  });
  vi.stubGlobal("fetch", fetchMock);
  open("owner");
  await screen.findByRole("heading", { name: "Request a new execution scope" });
  const button = screen.getByRole("button", { name: "Create pending scope" });
  fireEvent.change(screen.getByLabelText("New target name"), { target: { value: "Console scope" } });
  fireEvent.change(screen.getByLabelText(/Complete exact-origin/), { target: { value: "http://127.0.0.1:8765\nhttp://127.0.0.1:8766" } });
  fireEvent.change(screen.getByLabelText(/Reason for this requested/), { target: { value: "Owned synthetic console fixture." } });
  expect(button).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(button);
  await waitFor(() => expect(requested).toEqual({ name: "Console scope", origins: ["http://127.0.0.1:8765", "http://127.0.0.1:8766"], request_basis: "Owned synthetic console fixture." }));
  expect(await screen.findByRole("link", { name: "Review authorization status and scope" })).toHaveAttribute("href", "/targets/target-2/authorization");
  expect(fetchMock.mock.calls.some(([url]) => url.includes("/authorization"))).toBe(false);
});

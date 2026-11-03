import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { api, type Application, type TestRun } from "../../lib/api";
import { ApplicationRunsPage } from "../applications/ApplicationRunsPage";
import { RunsPage } from "./RunsPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const applications = ["Jev", "Other"].map((name, index) => ({
  id: `app-${index}`, name, status: "active", description: `${name} application`,
  workspace_id: "workspace", created_by_user_id: "user",
})) satisfies Application[];
const runs = (["completed", "awaiting_human"] as const).map((status, index) => ({
  id: `run-${index}`, application_id: "app-0", status,
  workspace_id: "workspace", target_id: "target", created_by_user_id: "user",
  configuration_snapshot: { test_name: index === 0 ? "Checkout" : "Sign in" },
  target_snapshot: { name: "Staging" },
  created_at: index === 0 ? "2026-10-18T11:00:00Z" : "2026-10-19T11:00:00Z",
})) satisfies TestRun[];

function mount(role = "owner") {
  function Context() { return <Outlet context={{ user: { id: "user" }, workspace: { id: "workspace", role } }} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs"]}><Routes><Route element={<Context />}>
    <Route path="/runs" element={<RunsPage />} />
    <Route path="/applications/:applicationId/runs" element={<ApplicationRunsPage />} />
  </Route></Routes></MemoryRouter></QueryClientProvider>);
  return client;
}

it("opens applications first, then loads only the selected application's tests", async () => {
  vi.spyOn(api, "listApplications").mockResolvedValue(applications);
  const list = vi.spyOn(api, "listRuns").mockResolvedValue(runs);
  vi.spyOn(api, "getApplication").mockResolvedValue(applications[0]);
  mount();
  await screen.findByText("Jev");
  expect(list).not.toHaveBeenCalled();
  await userEvent.type(screen.getByRole("searchbox", { name: "Find an application" }), "jev");
  expect(screen.queryByText("Other")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("link", { name: /Jev.*View tests/ }));
  await screen.findByText(/Checkout/);
  expect(list).toHaveBeenCalledExactlyOnceWith("app-0");
  expect(screen.getByRole("link", { name: /Sign in/ })).toHaveAttribute("href", "/runs/run-1/human-action");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Filter tests by status" }), "awaiting_human");
  expect(screen.queryByText(/Checkout/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(screen.getByText(/Checkout/)).toBeInTheDocument();
  await userEvent.type(screen.getByRole("searchbox", { name: "Find a test" }), "missing");
  expect(screen.getByRole("heading", { name: "No matching tests" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("link", { name: "All tests" }));
  await screen.findByText("Other");
});

it("retries an application load and keeps the empty directory useful for readers", async () => {
  vi.spyOn(api, "listApplications").mockRejectedValueOnce(new Error("Unavailable")).mockResolvedValue([]);
  mount("viewer");
  await screen.findByRole("button", { name: "Try again" });
  await userEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByRole("heading", { name: "No applications yet" });
  expect(screen.queryByRole("link", { name: "Add application" })).not.toBeInTheDocument();
});

it("sorts by actual creation time and keeps the application's status current", async () => {
  vi.spyOn(api, "listApplications").mockResolvedValue(applications);
  const list = vi.spyOn(api, "listRuns").mockResolvedValue(runs);
  vi.spyOn(api, "getApplication").mockResolvedValue(applications[0]);
  const client = mount();
  await userEvent.click(await screen.findByRole("link", { name: /Jev.*View tests/ }));
  await screen.findByText(/Checkout/);
  const testLinks = () => screen.getAllByRole("link").filter((link) => /\/runs\/run-/.test(link.getAttribute("href") ?? ""));
  expect(testLinks()[0]).toHaveTextContent("Sign in");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Sort tests" }), "oldest");
  expect(testLinks()[0]).toHaveTextContent("Checkout");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Filter tests by status" }), "awaiting_human");
  expect(testLinks()).toHaveLength(1);
  list.mockResolvedValue(runs.map((run) => ({ ...run, status: "completed" })));
  await act(async () => { await client.invalidateQueries({ queryKey: ["application-tests"] }); });
  await waitFor(() => expect(screen.getByRole("heading", { name: "No matching tests" })).toBeInTheDocument());
});

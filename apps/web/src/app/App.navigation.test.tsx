import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { ApiError, api, type TestRun } from "../lib/api";

const user = { id: "user", email: "owner@example.test", normalized_email: "owner@example.test", display_name: "Owner" };
const workspace = { id: "workspace", name: "Live workspace", role: "owner", status: "active" };
const app = { id: "app", workspace_id: workspace.id, created_by_user_id: user.id, name: "Actual storefront", description: null, status: "active" };
const clients: QueryClient[] = [];
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks(); });

function mount(path: string) {
  window.history.replaceState({}, "", path);
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clients.push(client);
  return render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
}

it("requires authentication for the live dashboard instead of displaying sample results", async () => {
  vi.spyOn(api, "me").mockRejectedValue(new ApiError("Sign in required", 401));
  const list = vi.spyOn(api, "listApplications");
  mount("/dashboard");
  await screen.findByRole("textbox", { name: /email/i });
  expect(window.location.pathname).toBe("/login");
  expect(screen.queryByText("Thread & Co.")).not.toBeInTheDocument();
  expect(list).not.toHaveBeenCalled();
});

it("keeps sample reports public only at an explicit example address", async () => {
  vi.spyOn(api, "me").mockRejectedValue(new ApiError("Sign in required", 401));
  mount("/examples/results");
  expect(await screen.findByRole("heading", { name: "Not ready yet", level: 1 })).toBeVisible();
  expect(screen.getByText("Sample data")).toBeVisible();
});

it("uses actual workspace tests and sends contract approval to its owner review screen", async () => {
  vi.spyOn(api, "me").mockResolvedValue(user);
  vi.spyOn(api, "listWorkspaces").mockResolvedValue([workspace]);
  vi.spyOn(api, "listApplications").mockResolvedValue([app]);
  const tests: TestRun[] = [
    { id: "review", status: "awaiting_human", configuration_snapshot: { test_name: "Review actual checks", execution_mode: "discovery_contract_v1", discovery_stage: "awaiting_approval" } },
    { id: "live", status: "running", configuration_snapshot: { test_name: "Actual active test" }, status_reason: "Testing the checkout" },
    { id: "done", status: "completed", configuration_snapshot: { test_name: "Actual finished test" } },
    { id: "replay", status: "draft", configuration_snapshot: { test_name: "Approved source replay", frozen_contract_source_run_id: "source-run", test_contract: { status: "approved" } } },
    { id: "draft", status: "draft", configuration_snapshot: { test_name: "Ordinary draft" } },
  ].map(test => ({ ...test, workspace_id: workspace.id, application_id: app.id, target_id: "target", created_by_user_id: user.id, target_snapshot: {} })) as TestRun[];
  vi.spyOn(api, "listRuns").mockResolvedValue(tests);
  mount("/overview");
  await screen.findByRole("heading", { name: "Dashboard", level: 1 });
  expect(screen.getByRole("link", { name: /Approve the tests/ })).toHaveAttribute("href", "/runs/review/contract");
  expect(screen.getByRole("link", { name: /Watch live/ })).toHaveAttribute("href", "/runs/live/watch");
  expect(screen.getByRole("link", { name: /See test results/ })).toHaveAttribute("href", "/runs/done/results");
  expect(within(screen.getByRole("region", { name: "Needs your help" })).getByRole("link", { name: /Run approved tests/ })).toHaveAttribute("href", "/runs/replay/contract");
  expect(screen.getAllByRole("link", { name: /Run approved tests/ })).toHaveLength(1);
  const drafts = within(screen.getByRole("region", { name: "Draft tests" }));
  expect(drafts.getByRole("link", { name: /Review draft/ })).toHaveAttribute("href", "/runs/draft/overview");
  expect(drafts.queryByText("Approved source replay")).not.toBeInTheDocument();
  expect(screen.getByText("Testing the checkout")).toBeVisible();
  expect(screen.queryByText("Sample data")).not.toBeInTheDocument();
  expect(screen.queryByText("Thread & Co.")).not.toBeInTheDocument();
  expect(window.location.pathname).toBe("/dashboard");
});

it("keeps the empty dashboard read-only for viewers", async () => {
  vi.spyOn(api, "me").mockResolvedValue(user);
  vi.spyOn(api, "listWorkspaces").mockResolvedValue([{ ...workspace, role: "viewer" }]);
  vi.spyOn(api, "listApplications").mockResolvedValue([]);
  mount("/dashboard");
  await screen.findByText("Your dashboard will live here.");
  expect(screen.queryByRole("link", { name: "Add an app" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Start a test" })).not.toBeInTheDocument();
});

it("carries a landing URL through sign-in and app creation into target authorization setup", async () => {
  vi.spyOn(api, "me").mockRejectedValue(new ApiError("Sign in required", 401));
  vi.spyOn(api, "login").mockResolvedValue(user);
  vi.spyOn(api, "listWorkspaces").mockResolvedValue([workspace]);
  vi.spyOn(api, "createApplication").mockResolvedValue(app);
  const createTarget = vi.spyOn(api, "createTarget");
  mount("/");
  const url = "https://storefront.example.test/checkout?plan=team";
  const input = screen.getAllByRole("textbox", { name: "YOUR APP'S ADDRESS" })[0];
  fireEvent.change(input, { target: { value: url } });
  fireEvent.submit(input.closest("form")!);
  await screen.findByRole("textbox", { name: /email/i });
  const events = userEvent.setup();
  await events.type(screen.getByRole("textbox", { name: /email/i }), user.email);
  await events.click(screen.getByRole("button", { name: "Continue to workspace" }));
  const name = await screen.findByRole("textbox", { name: /^Name/ });
  await events.type(name, app.name);
  await events.click(screen.getByRole("button", { name: "Add an app" }));
  await waitFor(() => expect(window.location.pathname).toBe("/applications/app/targets/new"));
  expect(await screen.findByRole("textbox", { name: /Base URL/i })).toHaveValue(url);
  expect(createTarget).not.toHaveBeenCalled();
});

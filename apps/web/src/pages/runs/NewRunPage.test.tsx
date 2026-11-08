import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { AppShellContext } from "../../layouts/AppShell";
import { api, type Target } from "../../lib/api";
import { NewRunPage } from "./NewRunPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it.each([
  ["legacy_persona", "target"], ["deep_feature_v1", "target"],
  ["legacy_persona", "second"], ["legacy_persona", "missing"],
])("creates a protected %s run and retains requested target %s", async (mode, requested) => {
  const user = userEvent.setup();
  vi.spyOn(api, "getApplication").mockResolvedValue({ id: "app", name: "Fixture", status: "active" } as Awaited<ReturnType<typeof api.getApplication>>);
  vi.spyOn(api, "listTargets").mockResolvedValue([{
    id: "target", name: "Protected fixture", status: "active", requires_auth: true,
    base_url: "https://fixture.test", environment: "production", allowed_origins: [],
  } as unknown as Target, {
    id: "second", name: "Second target", status: "active", requires_auth: true,
    base_url: "https://second.test", environment: "production", allowed_origins: [],
  } as unknown as Target]);
  vi.spyOn(api, "getAuthorization").mockResolvedValue({ status: "authorized", expires_at: null } as Awaited<ReturnType<typeof api.getAuthorization>>);
  vi.spyOn(api, "listIngestion").mockResolvedValue([]);
  const create = vi.spyOn(api, "createRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.createRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/applications/app/runs/new?target=${requested}&mode=${mode}`]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/applications/:applicationId/runs/new" element={<NewRunPage />} />
      <Route path="/runs/:runId/overview" element={<p>Created run</p>} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("button", { name: "Create test" });
  if (requested === "missing") {
    expect(screen.getByRole("combobox", { name: /^Application target/ })).toHaveValue("");
    // Phase 2d: a field's own message is a FieldError linked by
    // aria-describedby, not a role="alert" (the summary owns alerts).
    expect(screen.getByText(/requested target is unavailable/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /^Application target/ })).toHaveAttribute("aria-describedby", "test-target-error");
    expect(create).not.toHaveBeenCalled();
    await user.selectOptions(screen.getByRole("combobox", { name: /^Application target/ }), "second");
  } else expect(screen.getByRole("combobox", { name: /^Application target/ })).toHaveValue(requested);
  expect(screen.queryByLabelText(/marker|account reference|authentication origin|Enable verified/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Authentication assistance" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Testing mode")).toHaveValue(mode);
  fireEvent.change(screen.getByLabelText(/^Your testing goal/), { target: { value: "Check the protected account page" } });
  await user.click(screen.getByRole("button", { name: "Create test" }));
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(create.mock.calls[0]?.[1]).toBe(requested === "missing" ? "second" : requested);
  expect(create.mock.calls[0]?.[6]).toBe(mode);
  expect(create.mock.calls[0]?.[7]).toBeUndefined();
  expect(create.mock.calls[0]?.[11]).toBeUndefined();
  expect(create.mock.calls[0]?.[12]).toBe(true);
  expect(await screen.findByText("Created run")).toBeInTheDocument();
});

it("defaults new tests to exploration and opens contract review after starting discovery", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "getApplication").mockResolvedValue({ id: "app", name: "Fixture", status: "active" } as Awaited<ReturnType<typeof api.getApplication>>);
  vi.spyOn(api, "listTargets").mockResolvedValue([{
    id: "target", name: "Authorized fixture", status: "active", requires_auth: false,
    base_url: "https://fixture.test", environment: "production", allowed_origins: [],
  } as unknown as Target]);
  vi.spyOn(api, "getAuthorization").mockResolvedValue({ status: "authorized", expires_at: null } as Awaited<ReturnType<typeof api.getAuthorization>>);
  vi.spyOn(api, "listIngestion").mockResolvedValue([]);
  const create = vi.spyOn(api, "createRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.createRun>>);
  const start = vi.spyOn(api, "startRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.startRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/applications/app/runs/new?target=target"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/applications/:applicationId/runs/new" element={<NewRunPage />} />
      <Route path="/runs/:runId/contract" element={<p>Review discovered tests</p>} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("button", { name: "Explore the app" });
  expect(screen.getByLabelText("Testing mode")).toHaveValue("discovery_contract_v1");
  const app = screen.getByRole("combobox", { name: /^App \(required\)/ });
  const appUrl = screen.getByRole("textbox", { name: "App URL" });
  expect(appUrl).toHaveValue("https://fixture.test");
  expect(appUrl).toHaveAttribute("readonly");
  expect(appUrl).toHaveClass("text-input");
  expect(appUrl.closest(".composer-target")).toBeNull();
  expect(app.compareDocumentPosition(appUrl) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  fireEvent.change(screen.getByLabelText(/^What is this app and who is it for/), { target: { value: "A storefront for local shoppers." } });
  await user.click(screen.getByRole("button", { name: "Explore the app" }));
  expect(await screen.findByText("Review discovered tests")).toBeInTheDocument();
  expect(create).toHaveBeenCalledOnce();
  expect(create.mock.calls[0]?.[6]).toBe("discovery_contract_v1");
  expect(create.mock.calls[0]?.[12]).toBe(false);
  expect(start).toHaveBeenCalledExactlyOnceWith("run");
  expect(create.mock.invocationCallOrder[0]).toBeLessThan(start.mock.invocationCallOrder[0]);
});

it("renders the harness option disabled as not available yet and keeps the current default", async () => {
  vi.spyOn(api, "getApplication").mockResolvedValue({ id: "app", name: "Fixture", status: "active" } as Awaited<ReturnType<typeof api.getApplication>>);
  vi.spyOn(api, "listTargets").mockResolvedValue([{
    id: "target", name: "Authorized fixture", status: "active", requires_auth: false,
    base_url: "https://fixture.test", environment: "production", allowed_origins: [],
  } as unknown as Target]);
  vi.spyOn(api, "getAuthorization").mockResolvedValue({ status: "authorized", expires_at: null } as Awaited<ReturnType<typeof api.getAuthorization>>);
  vi.spyOn(api, "listIngestion").mockResolvedValue([]);
  vi.spyOn(api, "createRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.createRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/applications/app/runs/new?target=target"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/applications/:applicationId/runs/new" element={<NewRunPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("button", { name: "Explore the app" });
  expect(screen.getByLabelText("Testing mode")).toHaveValue("discovery_contract_v1");
  // The unavailability note is attached to the disabled option itself,
  // not a floating line under the select (examination, New test).
  expect(screen.getByRole("option", { name: "Full test — checks every interaction (not available yet)" })).toBeDisabled();
  expect(screen.queryByText("Not available yet")).not.toBeInTheDocument();
});

it("posts harness_v1 when the harness mode is preselected", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "getApplication").mockResolvedValue({ id: "app", name: "Fixture", status: "active" } as Awaited<ReturnType<typeof api.getApplication>>);
  vi.spyOn(api, "listTargets").mockResolvedValue([{
    id: "target", name: "Authorized fixture", status: "active", requires_auth: false,
    base_url: "https://fixture.test", environment: "production", allowed_origins: [],
  } as unknown as Target]);
  vi.spyOn(api, "getAuthorization").mockResolvedValue({ status: "authorized", expires_at: null } as Awaited<ReturnType<typeof api.getAuthorization>>);
  vi.spyOn(api, "listIngestion").mockResolvedValue([]);
  const create = vi.spyOn(api, "createRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.createRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/applications/app/runs/new?target=target&mode=harness_v1"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/applications/:applicationId/runs/new" element={<NewRunPage />} />
      <Route path="/runs/:runId/overview" element={<p>Created run</p>} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("button", { name: "Create test" });
  expect(screen.getByLabelText("Testing mode")).toHaveValue("harness_v1");
  expect(screen.getByText("The agent explores your app, checks every button, field and link it finds, and proves every problem twice before reporting it.")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/^Your testing goal/), { target: { value: "Check the protected account page" } });
  await user.click(screen.getByRole("button", { name: "Create test" }));
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(create.mock.calls[0]?.[6]).toBe("harness_v1");
  expect(await screen.findByText("Created run")).toBeInTheDocument();
});

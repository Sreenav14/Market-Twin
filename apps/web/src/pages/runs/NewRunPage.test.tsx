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
  ["legacy_persona", "target", "persona"], ["deep_feature_v1", "target", "explore_test"],
  ["legacy_persona", "second", "persona"], ["legacy_persona", "missing", "persona"],
])("creates a protected %s run and retains requested target %s", async (mode, requested, kind) => {
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
  const create = vi.spyOn(api, "createRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.createRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/applications/app/runs/new?target=${requested}&mode=${mode}`]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/applications/:applicationId/runs/new" element={<NewRunPage />} />
      <Route path="/runs/:runId/overview" element={<p>Created run</p>} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("button", { name: "Create test" });
  const targetBox = () => screen.getByRole("combobox", { name: kind === "explore_test" ? /^App/ : /^Application target/ });
  if (requested === "missing") {
    expect(targetBox()).toHaveValue("");
    // Phase 2d: a field's own message is a FieldError linked by
    // aria-describedby, not a role="alert" (the summary owns alerts).
    expect(screen.getByText(/requested target is unavailable/)).toBeInTheDocument();
    expect(targetBox()).toHaveAttribute("aria-describedby", "test-target-error");
    expect(create).not.toHaveBeenCalled();
    await user.selectOptions(targetBox(), "second");
  } else expect(targetBox()).toHaveValue(requested);
  expect(screen.queryByLabelText(/marker|account reference|authentication origin|Enable verified/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Authentication assistance" })).not.toBeInTheDocument();
  expect(screen.getByRole("radio", { name: kind === "persona" ? "Persona Test" : "Explore & Test" })).toBeChecked();
  fireEvent.change(screen.getByLabelText(kind === "persona" ? /^Your testing goal/ : /^What is this app and who is it for/), { target: { value: "Check the protected account page" } });
  await user.click(screen.getByRole("button", { name: "Create test" }));
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(create.mock.calls[0]?.[1]).toBe(requested === "missing" ? "second" : requested);
  expect(create.mock.calls[0]?.[5]).toBe(kind);
  expect(create.mock.calls[0]?.[6]).toBeUndefined();
  expect(create.mock.calls[0]?.[10]).toBeUndefined();
  expect(create.mock.calls[0]?.[11]).toBe(true);
  expect(await screen.findByText("Created run")).toBeInTheDocument();
});

it("defaults new tests to Explore & Test and opens the overview after creating", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "getApplication").mockResolvedValue({ id: "app", name: "Fixture", status: "active" } as Awaited<ReturnType<typeof api.getApplication>>);
  vi.spyOn(api, "listTargets").mockResolvedValue([{
    id: "target", name: "Authorized fixture", status: "active", requires_auth: false,
    base_url: "https://fixture.test", environment: "production", allowed_origins: [],
  } as unknown as Target]);
  vi.spyOn(api, "getAuthorization").mockResolvedValue({ status: "authorized", expires_at: null } as Awaited<ReturnType<typeof api.getAuthorization>>);
  const create = vi.spyOn(api, "createRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.createRun>>);
  const start = vi.spyOn(api, "startRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.startRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/applications/app/runs/new?target=target"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/applications/:applicationId/runs/new" element={<NewRunPage />} />
      <Route path="/runs/:runId/overview" element={<p>Created run</p>} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("button", { name: "Create test" });
  expect(screen.getByRole("radio", { name: "Explore & Test" })).toBeChecked();
  const app = screen.getByRole("combobox", { name: /^App \(required\)/ });
  const appUrl = screen.getByRole("textbox", { name: "App URL" });
  expect(appUrl).toHaveValue("https://fixture.test");
  expect(appUrl).toHaveAttribute("readonly");
  expect(appUrl).toHaveClass("text-input");
  expect(appUrl.closest(".composer-target")).toBeNull();
  expect(app.compareDocumentPosition(appUrl) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  fireEvent.change(screen.getByLabelText(/^What is this app and who is it for/), { target: { value: "A storefront for local shoppers." } });
  await user.click(screen.getByRole("button", { name: "Create test" }));
  expect(await screen.findByText("Created run")).toBeInTheDocument();
  expect(create).toHaveBeenCalledOnce();
  expect(create.mock.calls[0]?.[5]).toBe("explore_test");
  expect(create.mock.calls[0]?.[11]).toBe(true);
  expect(start).not.toHaveBeenCalled();
});

it("offers Explore & Test as the enabled default kind", async () => {
  vi.spyOn(api, "getApplication").mockResolvedValue({ id: "app", name: "Fixture", status: "active" } as Awaited<ReturnType<typeof api.getApplication>>);
  vi.spyOn(api, "listTargets").mockResolvedValue([{
    id: "target", name: "Authorized fixture", status: "active", requires_auth: false,
    base_url: "https://fixture.test", environment: "production", allowed_origins: [],
  } as unknown as Target]);
  vi.spyOn(api, "getAuthorization").mockResolvedValue({ status: "authorized", expires_at: null } as Awaited<ReturnType<typeof api.getAuthorization>>);
  vi.spyOn(api, "createRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.createRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/applications/app/runs/new?target=target"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/applications/:applicationId/runs/new" element={<NewRunPage />} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("button", { name: "Create test" });
  expect(screen.getByRole("radio", { name: "Explore & Test" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "Explore & Test" })).not.toBeDisabled();
  expect(screen.getByRole("radio", { name: "Persona Test" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Check the look" })).toBeInTheDocument();
});

it("maps a preselected harness_v1 link to Explore & Test", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "getApplication").mockResolvedValue({ id: "app", name: "Fixture", status: "active" } as Awaited<ReturnType<typeof api.getApplication>>);
  vi.spyOn(api, "listTargets").mockResolvedValue([{
    id: "target", name: "Authorized fixture", status: "active", requires_auth: false,
    base_url: "https://fixture.test", environment: "production", allowed_origins: [],
  } as unknown as Target]);
  vi.spyOn(api, "getAuthorization").mockResolvedValue({ status: "authorized", expires_at: null } as Awaited<ReturnType<typeof api.getAuthorization>>);
  const create = vi.spyOn(api, "createRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.createRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/applications/app/runs/new?target=target&mode=harness_v1"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/applications/:applicationId/runs/new" element={<NewRunPage />} />
      <Route path="/runs/:runId/overview" element={<p>Created run</p>} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("button", { name: "Create test" });
  expect(screen.getByRole("radio", { name: "Explore & Test" })).toBeChecked();
  expect(screen.getByText(/The agent explores your app, checks every button, field and link it finds/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/^What is this app and who is it for/), { target: { value: "Check the protected account page" } });
  await user.click(screen.getByRole("button", { name: "Create test" }));
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(create.mock.calls[0]?.[5]).toBe("explore_test");
  expect(await screen.findByText("Created run")).toBeInTheDocument();
});

it("offers the run mode for Explore & Test only, with the data editor behind Standard (W2)", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "getApplication").mockResolvedValue({ id: "app", name: "Fixture", status: "active" } as Awaited<ReturnType<typeof api.getApplication>>);
  vi.spyOn(api, "listTargets").mockResolvedValue([{
    id: "target", name: "Authorized fixture", status: "active", requires_auth: false,
    base_url: "https://fixture.test", environment: "production", allowed_origins: [],
  } as unknown as Target]);
  vi.spyOn(api, "getAuthorization").mockResolvedValue({ status: "authorized", expires_at: null } as Awaited<ReturnType<typeof api.getAuthorization>>);
  const create = vi.spyOn(api, "createRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.createRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/applications/app/runs/new?target=target"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/applications/:applicationId/runs/new" element={<NewRunPage />} />
      <Route path="/runs/:runId/overview" element={<p>Created run</p>} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("button", { name: "Create test" });
  // Read-only is pre-selected and the approved-data editor is absent.
  expect(screen.getByRole("radio", { name: "Read-only" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "Standard" })).not.toBeChecked();
  expect(screen.queryByRole("button", { name: "Add test data" })).not.toBeInTheDocument();
  // Selecting Standard reveals the editor; a row can be filled in.
  await user.click(screen.getByRole("radio", { name: "Standard" }));
  await user.click(screen.getByRole("button", { name: "Add test data" }));
  fireEvent.change(screen.getByLabelText("Test data key 1"), { target: { value: "company_name" } });
  fireEvent.change(screen.getByLabelText("Test data value 1"), { target: { value: "Thread & Co. Test" } });
  // Switching to Persona Test hides the whole run-mode control.
  await user.click(screen.getByRole("radio", { name: "Persona Test" }));
  expect(screen.queryByRole("radio", { name: "Read-only" })).not.toBeInTheDocument();
  expect(screen.queryByRole("radio", { name: "Standard" })).not.toBeInTheDocument();
  // Back on Explore & Test the selection survives and reaches createRun.
  await user.click(screen.getByRole("radio", { name: "Explore & Test" }));
  expect(screen.getByRole("radio", { name: "Standard" })).toBeChecked();
  fireEvent.change(screen.getByLabelText(/^What is this app and who is it for/), { target: { value: "A storefront for local shoppers." } });
  await user.click(screen.getByRole("button", { name: "Create test" }));
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(create.mock.calls[0]?.[13]).toBe("standard");
  expect(create.mock.calls[0]?.[14]).toEqual([{ key: "company_name", value: "Thread & Co. Test" }]);
  expect(await screen.findByText("Created run")).toBeInTheDocument();
});

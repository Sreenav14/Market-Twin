import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { AppShellContext } from "../../layouts/AppShell";
import { api, type Target } from "../../lib/api";
import { NewRunPage } from "./NewRunPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it.each(["legacy_persona", "deep_feature_v1"])("creates a protected %s run without asking for login setup", async (mode) => {
  const user = userEvent.setup();
  vi.spyOn(api, "getApplication").mockResolvedValue({ id: "app", name: "Fixture", status: "active" } as Awaited<ReturnType<typeof api.getApplication>>);
  vi.spyOn(api, "listTargets").mockResolvedValue([{
    id: "target", name: "Protected fixture", status: "active", requires_auth: true,
    base_url: "https://fixture.test", environment: "production", allowed_origins: [],
  } as unknown as Target]);
  vi.spyOn(api, "getAuthorization").mockResolvedValue({ status: "authorized", expires_at: null } as Awaited<ReturnType<typeof api.getAuthorization>>);
  vi.spyOn(api, "listIngestion").mockResolvedValue([]);
  const create = vi.spyOn(api, "createRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.createRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function ContextOutlet() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/applications/app/tests/new"]}>
    <Routes><Route element={<ContextOutlet />}><Route path="/applications/:applicationId/tests/new" element={<NewRunPage />} />
      <Route path="/runs/:runId/overview" element={<p>Created run</p>} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("button", { name: "Create test" });
  expect(screen.queryByLabelText(/marker|account reference|authentication origin|Enable verified/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Authentication assistance" })).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Testing mode"), mode);
  await user.type(screen.getByLabelText("Your testing goal"), "Check the protected account page");
  await user.click(screen.getByRole("button", { name: "Create test" }));
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(create.mock.calls[0]?.[7]).toBeUndefined();
  expect(create.mock.calls[0]?.[11]).toBeUndefined();
  expect(create.mock.calls[0]?.[12]).toBe(true);
  expect(await screen.findByText("Created run")).toBeInTheDocument();
});

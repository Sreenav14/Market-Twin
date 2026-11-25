import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { AppShellContext } from "../../layouts/AppShell";
import { api, type Application, type Target } from "../../lib/api";
import { NAV_COMMANDS } from "../../lib/navCommands";
import { UiSlopPage } from "./UiSlopPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("creates a preselected UI audit without a prompt and retains authorized target checks", async () => {
  const user = userEvent.setup();
  const app = { id: "app", name: "Fixture", status: "active" } as Application;
  vi.spyOn(api, "listApplications").mockResolvedValue([app]);
  vi.spyOn(api, "getApplication").mockResolvedValue(app);
  vi.spyOn(api, "listTargets").mockResolvedValue([{ id: "target", name: "Production", status: "active",
    base_url: "https://fixture.test/", environment: "production", allowed_origins: [] } as unknown as Target]);
  vi.spyOn(api, "getAuthorization").mockResolvedValue({ status: "authorized", expires_at: null } as Awaited<ReturnType<typeof api.getAuthorization>>);
  const create = vi.spyOn(api, "createRun").mockResolvedValue({ id: "run" } as Awaited<ReturnType<typeof api.createRun>>);
  const context = { user: { id: "user" }, workspace: { id: "workspace", role: "owner" } } as AppShellContext;
  function Context() { return <Outlet context={context} />; }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/runs/new?mode=slop"]}>
    <Routes><Route element={<Context />}><Route path="/runs/new" element={<UiSlopPage />} />
      <Route path="/runs/:runId/overview" element={<p>Created audit</p>} /></Route></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("option", { name: "Fixture" });
  await user.selectOptions(screen.getByLabelText("Application"), "app");
  const submit = await screen.findByRole("button", { name: "Create UI audit" });
  expect(screen.queryByRole("textbox", { name: /testing goal|who is it for/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Kind of test" })).not.toBeInTheDocument();
  await user.click(submit);
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(create.mock.calls[0]?.[1]).toBe("target");
  expect(create.mock.calls[0]?.[2]).toContain("all discovered authorized pages and states");
  expect(create.mock.calls[0]?.[5]).toBe("slop");
  expect(await screen.findByText("Created audit")).toBeInTheDocument();
  expect(NAV_COMMANDS.map(command => command.title)).toEqual(["Home", "Apps", "Knowledge", "Tests", "Settings"]);
});

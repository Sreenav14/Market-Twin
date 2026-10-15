import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider, useOutletContext } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell, type AppShellContext } from "./AppShell";
import { api, type CurrentUser, type Workspace } from "../lib/api";

const user: CurrentUser = {
  id: "synthetic-user",
  email: "reviewer@example.test",
  normalized_email: "reviewer@example.test",
  display_name: "Synthetic reviewer",
};
const workspaces: Workspace[] = [
  { id: "workspace-one", name: "Alpha workspace", status: "active", role: "owner" },
  { id: "workspace-two", name: "Beta workspace", status: "active", role: "admin" },
];

function WorkspacePage() {
  const { workspace } = useOutletContext<AppShellContext>();
  return <h1>{workspace.name}</h1>;
}

function renderShell(initialEntry = "/overview") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const router = createMemoryRouter(
    [
      {
        element: <AppShell user={user} onLogout={vi.fn().mockResolvedValue(undefined)} />,
        children: [
          { path: "/overview", element: <WorkspacePage /> },
          { path: "/settings/profile", element: <WorkspacePage /> },
        ],
      },
    ],
    { initialEntries: [initialEntry] },
  );
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  };
}

describe("AppShell responsive navigation", () => {
  afterEach(() => vi.restoreAllMocks());

  it("closes the navigation drawer on Escape and restores focus to its trigger", async () => {
    vi.spyOn(api, "listWorkspaces").mockResolvedValue(workspaces);
    const userEvents = userEvent.setup();
    renderShell();

    const trigger = await screen.findByRole("button", { name: "Open navigation" });
    await userEvents.click(trigger);
    expect(await screen.findByRole("dialog", { name: "Workspace navigation" })).toBeVisible();

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Workspace navigation" })).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("closes the drawer and moves focus to the page after a navigation link", async () => {
    vi.spyOn(api, "listWorkspaces").mockResolvedValue(workspaces);
    const userEvents = userEvent.setup();
    renderShell("/settings/profile");

    await userEvents.click(await screen.findByRole("button", { name: "Open navigation" }));
    const dialog = await screen.findByRole("dialog", { name: "Workspace navigation" });
    await userEvents.click(within(dialog).getByRole("link", { name: "Overview" }));

    expect(await screen.findByRole("heading", { name: "Alpha workspace" })).toBeVisible();
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
  });

  it("removes the previous workspace cache before navigating after a workspace switch", async () => {
    vi.spyOn(api, "listWorkspaces").mockResolvedValue(workspaces);
    const userEvents = userEvent.setup();
    const { queryClient } = renderShell();
    queryClient.setQueryData(["workspace-private", "workspace-one"], { value: "old" });
    queryClient.setQueryData(["workspace-private", "workspace-two"], { value: "new" });

    await userEvents.click(await screen.findByRole("button", { name: "Open navigation" }));
    const dialog = await screen.findByRole("dialog", { name: "Workspace navigation" });
    const select = dialog.querySelector("#mobile-workspace-select");
    expect(select).toBeInstanceOf(HTMLSelectElement);
    await userEvents.selectOptions(select!, "workspace-two");

    expect(await screen.findByRole("heading", { name: "Beta workspace" })).toBeVisible();
    await waitFor(() => expect(queryClient.getQueryCache().findAll()).toHaveLength(0));
  });
});

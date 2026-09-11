import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LifecyclePanel } from "./LifecyclePanel";
import { api } from "../../lib/api";

describe("LifecyclePanel", () => {
  it("requires confirmation and preserves the item when cancelled", async () => {
    const remove = vi.spyOn(api, "deleteApplication").mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<MemoryRouter><QueryClientProvider client={new QueryClient()}><LifecyclePanel entityType="application" entityName="Acme Checkout" entityId="app" returnTo="/applications" /></QueryClientProvider></MemoryRouter>);
    await user.click(screen.getByRole("button", { name: "Delete application: Acme Checkout" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(remove).not.toHaveBeenCalled();
    remove.mockRestore();
  });
});

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Link, MemoryRouter, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { NewTargetPage } from "../targets/NewTargetPage";
import { NewApplicationPage } from "./NewApplicationPage";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function Shell() {
  const location = useLocation();
  return <><Link to="/elsewhere">Go elsewhere</Link><output aria-label="Current route">{location.pathname}</output>
    <Outlet context={{ workspace: { id: "ws-1", role: "owner" } }} /></>;
}

it.each(["application", "target"] as const)("keeps a pending %s save from overriding later navigation", async (kind) => {
  let finish!: (response: Response) => void;
  const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; }));
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRouter initialEntries={[kind === "application" ? "/applications/new" : "/applications/app-1/targets/new"]}>
    <Routes><Route element={<Shell />}>
      <Route path="/applications/new" element={<NewApplicationPage />} />
      <Route path="/applications/:applicationId/targets/new" element={<NewTargetPage />} />
      <Route path="/elsewhere" element={<p>Elsewhere</p>} />
      <Route path="*" element={<p>Unexpected save navigation</p>} />
    </Route></Routes>
  </MemoryRouter>);
  const name = screen.getByLabelText(kind === "application" ? /^Name/ : /^Target name/);
  fireEvent.change(name, { target: { value: "Storefront" } });
  fireEvent.click(screen.getByRole("button", { name: kind === "application" ? "Create application" : "Save target & review authorization" }));
  expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  expect(name).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("link", { name: "Go elsewhere" }));
  expect(screen.getByLabelText("Current route")).toHaveTextContent("/elsewhere");
  await act(async () => { finish(new Response(JSON.stringify({ id: "saved-1" }), { status: 200, headers: { "Content-Type": "application/json" } })); });
  expect(screen.getByLabelText("Current route")).toHaveTextContent("/elsewhere");
  expect(screen.queryByText("Unexpected save navigation")).not.toBeInTheDocument();
});

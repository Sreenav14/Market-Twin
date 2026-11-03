import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError, api } from "../../lib/api";
import { LoginPage } from "../auth/LoginPage";
import { AuthCallbackPage } from "../auth/AuthCallbackPage";
import { UnexpectedErrorPage } from "../system/UnexpectedErrorPage";
import { HowPage } from "./PublicPages";

beforeEach(() => { vi.spyOn(window, "scrollTo").mockImplementation(() => {}); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("keeps sign-in retryable after a service failure", async () => {
  const authenticated = vi.fn();
  const login = vi.spyOn(api, "login").mockRejectedValue(new ApiError("Unavailable", 503));
  render(<MemoryRouter><LoginPage onAuthenticated={authenticated} /></MemoryRouter>);
  fireEvent.change(screen.getByRole("textbox", { name: /email/i }), { target: { value: "owner@example.test" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue to workspace" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("The login service is unavailable");
  expect(login).toHaveBeenCalledWith("owner@example.test");
  expect(authenticated).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Continue to workspace" })).toBeEnabled();
});

it("hands the actual signed-in identity to the existing authentication callback", async () => {
  const user = { id: "owner", email: "owner@example.test", normalized_email: "owner@example.test", display_name: "Owner" };
  vi.spyOn(api, "login").mockResolvedValue(user);
  const authenticated = vi.fn();
  render(<MemoryRouter><LoginPage onAuthenticated={authenticated} /></MemoryRouter>);
  fireEvent.change(screen.getByRole("textbox", { name: /email/i }), { target: { value: user.email } });
  fireEvent.click(screen.getByRole("button", { name: "Continue to workspace" }));
  await vi.waitFor(() => expect(authenticated).toHaveBeenCalledWith(user));
});

it("does not simulate production authentication at the callback", () => {
  const login = vi.spyOn(api, "login");
  render(<MemoryRouter><AuthCallbackPage /></MemoryRouter>);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Production sign-in is not available here");
  expect(screen.getByRole("link", { name: "Return to sign in" })).toHaveAttribute("href", "/login");
  expect(login).not.toHaveBeenCalled();
});

it("explains repeat-check evidence and links to real app setup", () => {
  render(<MemoryRouter><HowPage /></MemoryRouter>);
  expect(screen.getByText(/Broken only when a repeat check also failed/)).toBeVisible();
  expect(screen.getByRole("link", { name: "Start a test" })).toHaveAttribute("href", "/applications/new");
  const missingEvidence = screen.getByText("Missing or uncaptured artifact");
  fireEvent.click(missingEvidence);
  expect(missingEvidence.closest("details")).toHaveAttribute("open");
  expect(screen.getByText(/Adjacent screenshots are never substituted/)).toBeVisible();
  expect(screen.queryByText("Sample data")).not.toBeInTheDocument();
});

it("keeps recovery actions without asserting the state of saved data", () => {
  render(<MemoryRouter><UnexpectedErrorPage /></MemoryRouter>);
  expect(screen.getByRole("button", { name: "Reload page" })).toBeEnabled();
  expect(screen.getByRole("link", { name: "Return to Dashboard" })).toHaveAttribute("href", "/dashboard");
  expect(screen.queryByText(/remain safe and unaffected/)).not.toBeInTheDocument();
});

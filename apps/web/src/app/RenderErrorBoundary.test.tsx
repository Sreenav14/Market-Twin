import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { RenderErrorBoundary } from "./RenderErrorBoundary";

it("renders a recoverable fallback without exception contents", () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  function Broken(): never { throw new Error("private backend payload"); }
  try {
    render(<RenderErrorBoundary><Broken /></RenderErrorBoundary>);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.getByRole("button", { name: "Reload MarketTwin" })).toBeInTheDocument();
    expect(screen.queryByText("private backend payload")).not.toBeInTheDocument();
  } finally { log.mockRestore(); }
});

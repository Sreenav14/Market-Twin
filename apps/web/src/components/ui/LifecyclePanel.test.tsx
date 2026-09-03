import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LifecyclePanel } from "./LifecyclePanel";

describe("LifecyclePanel", () => {
  it("keeps archive and delete disabled until backend lifecycle APIs exist", () => {
    render(<LifecyclePanel entityType="application" entityName="Acme Checkout" />);
    expect(screen.getByRole("button", { name: "Archive" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
    expect(screen.getByText(/preserves historical runs/i)).toBeInTheDocument();
  });
});

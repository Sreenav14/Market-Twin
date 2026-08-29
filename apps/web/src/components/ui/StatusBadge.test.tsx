import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders authorized as success", () => { render(<StatusBadge status="authorized" />); expect(screen.getByText("authorized")).toHaveClass("status-success"); });
  it("renders failed as danger", () => { render(<StatusBadge status="failed" />); expect(screen.getByText("failed")).toHaveClass("status-danger"); });
});

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Avatar } from "./Avatar";
import { Breadcrumbs } from "./Breadcrumbs";
import { CountBadge, NeutralTag } from "./StatusBadge";
import { LoadMore, Pagination } from "./Pagination";
import { ProgressBar } from "./Progress";

describe("Phase 2b display primitives", () => {
  it("Avatar: people are circles, personas and apps are squares", () => {
    const { container, rerender } = render(<Avatar kind="person" name="Sreenav N" />);
    expect(container.querySelector(".avatar-person")).not.toBeNull();
    expect(screen.queryByText("SN")).not.toBeNull();
    rerender(<Avatar kind="persona" name="Maya" />);
    expect(container.querySelector(".avatar-persona")).not.toBeNull();
    rerender(<Avatar kind="app" name="Thread Co" />);
    expect(container.querySelector(".avatar-app")).not.toBeNull();
  });

  it("Avatar: xs shows no initials (glyph fallback)", () => {
    const { container } = render(<Avatar kind="person" name="Sreenav" size="xs" />);
    expect(container.querySelector(".avatar-initials")).toBeNull();
  });

  it("CountBadge: numbers only, capped at 99+", () => {
    render(<CountBadge count={130} label="findings" />);
    expect(screen.getByText("99+")).not.toBeNull();
    expect(screen.getByRole("img", { name: "130 findings" })).not.toBeNull();
  });

  it("NeutralTag renders its category as plain outlined text", () => {
    render(<NeutralTag>production</NeutralTag>);
    expect(screen.getByText("production").className).toContain("tag-neutral");
  });

  it("LoadMore: one label shape with the count in words", () => {
    render(<LoadMore noun="steps" loaded={25} total={80} loading={false} onLoad={() => {}} />);
    expect(screen.getByRole("button", { name: "Load more steps" })).not.toBeNull();
    expect(screen.getByText("25 of 80 steps loaded")).not.toBeNull();
  });

  it("Pagination: current page is not a button and carries aria-current", () => {
    render(<Pagination page={3} totalPages={12} onPage={vi.fn()} />);
    const current = screen.getByText("3");
    expect(current.getAttribute("aria-current")).toBe("page");
    expect(current.tagName).toBe("SPAN");
    expect(screen.getByRole("button", { name: "Page 4" })).not.toBeNull();
    expect(screen.getByRole("button", { name: "Previous page" })).not.toBeNull();
  });

  it("ProgressBar: the aria value is the count, never a percentage", () => {
    render(<ProgressBar value={3} max={12} label="3 of 12 journeys finished" />);
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-valuenow")).toBe("3");
    expect(bar.getAttribute("aria-valuemax")).toBe("12");
    expect(bar.getAttribute("aria-valuetext")).toBe("3 of 12 journeys finished");
  });

  it("Breadcrumbs: last item is current, parents are links", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs
          items={[
            { label: "Tests", to: "/runs" },
            { label: "Findings", to: "/runs/r/findings" },
            { label: "Pay button does nothing" },
          ]}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Tests" })).not.toBeNull();
    const current = screen.getByText("Pay button does nothing");
    expect(current.getAttribute("aria-current")).toBe("page");
    expect(current.closest("a")).toBeNull();
  });
});

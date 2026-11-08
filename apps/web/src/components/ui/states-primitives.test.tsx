import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  EmptyState,
  LOADING_MIN_DISPLAY_MS,
  LOADING_SHOW_DELAY_MS,
  SkeletonPanel,
  Spinner,
  useDelayedLoading,
} from "./StateViews";
import { VoiceCard } from "./VoiceCard";
import { RenderErrorBoundary } from "../../app/RenderErrorBoundary";

describe("Phase 2e states & micro contracts", () => {
  it("loading timing constants are the adopted interims (300ms show-delay, 500ms minimum-display)", () => {
    expect(LOADING_SHOW_DELAY_MS).toBe(300);
    expect(LOADING_MIN_DISPLAY_MS).toBe(500);
  });

  it("spinner renders the re-registered loop element on the size ladder", () => {
    const { container } = render(<Spinner size={32} />);
    const el = container.querySelector(".spinner");
    expect(el).not.toBeNull();
    expect(el?.className).toContain("spinner-lg");
  });

  it("useDelayedLoading shows nothing before the 300ms show-delay", () => {
    vi.useFakeTimers();
    function Probe({ active }: { active: boolean }) {
      const shown = useDelayedLoading(active);
      return <p>{shown ? "shown" : "hidden"}</p>;
    }
    const { rerender } = render(<Probe active />);
    expect(screen.getByText("hidden")).toBeTruthy();
    act(() => vi.advanceTimersByTime(299));
    expect(screen.getByText("hidden")).toBeTruthy();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByText("shown")).toBeTruthy();
    rerender(<Probe active={false} />);
    act(() => vi.advanceTimersByTime(499));
    expect(screen.getByText("shown")).toBeTruthy();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByText("hidden")).toBeTruthy();
    vi.useRealTimers();
  });

  it("static skeleton is bars only — no text content, no fake rows", () => {
    const { container } = render(<SkeletonPanel label="Loading tests" rows={3} />);
    expect(screen.getByRole("status", { name: "Loading tests" })).toBeTruthy();
    expect(container.querySelectorAll(".skeleton-bar").length).toBeGreaterThanOrEqual(3);
    expect(container.textContent).toBe("");
  });

  it("empty state renders an action only when one is passed", () => {
    const { container, rerender } = render(<EmptyState title="Start by adding a target" copy="Targets appear here." />);
    expect(screen.queryByRole("button")).toBeNull();
    rerender(
      <EmptyState title="Start by adding a target" copy="Targets appear here." action={<button type="button">Add a target</button>} />,
    );
    expect(screen.getByRole("button", { name: "Add a target" })).toBeTruthy();
    expect(container.querySelector(".empty-mark svg")).not.toBeNull();
  });

  it("voice card: impressions wear the band, checks-side quotes do not", () => {
    const { container, rerender } = render(<VoiceCard name="Maya" quote="The pay button does nothing." />);
    expect(container.querySelector(".voice-card-band")).not.toBeNull();
    expect(container.querySelector(".voice-quote p")?.textContent).toContain("The pay button does nothing.");
    rerender(<VoiceCard name="Maya" quote="The pay button does nothing." band={false} />);
    expect(container.querySelector(".voice-card-band")).toBeNull();
    expect(container.querySelector(".voice-card")).not.toBeNull();
  });

  it("the root error boundary's button sits on the landed button recipe", () => {
    function Broken(): never {
      throw new Error("boom");
    }
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <RenderErrorBoundary>
        <Broken />
      </RenderErrorBoundary>,
    );
    const button = screen.getByRole("button", { name: "Reload MarketTwin" });
    expect(button.className).toContain("primary-button");
    spy.mockRestore();
  });
});

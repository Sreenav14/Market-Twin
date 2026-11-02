import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { CANONICAL_DEMO_DATA } from "../lib/concept-dataset";
import {
  CoverageBar,
  MegaMenu,
  NeedsYouRow,
  ProofChip,
  ProofTrail,
  StatusPill,
  StepList,
  TakeoverPanel,
  UrlIntakeForm,
  VerdictBlock,
  VerdictStrip,
} from "../components/concept";
import {
  DashboardPage,
  LandingPage,
  TestResultsPage,
  WatchLivePage,
} from "../pages/concept";

afterEach(() => {
  cleanup();
});

describe("MarketTwin Arize-Inspired Concept Acceptance (§15, §15A)", () => {
  describe("Data Integrity (D1–D8)", () => {
    it("D1: Test results displays verbatim totals, verdict word and honest-inputs strip", () => {
      render(<TestResultsPage data={CANONICAL_DEMO_DATA} />);

      // Exactly once: "11 of the 14 attempts we could check worked."
      const headlineMatches = screen.getAllByText(
        "11 of the 14 attempts we could check worked."
      );
      expect(headlineMatches).toHaveLength(1);

      // Verdict word is H1
      const h1 = screen.getByRole("heading", { level: 1 });
      expect(h1).toHaveTextContent("Not ready yet");

      // Honest inputs strip
      expect(
        screen.getByText(
          "14 of 18 attempts checked · 3 testers · 2 problems confirmed · Sat 31 Oct 2026"
        )
      ).toBeInTheDocument();
    });

    it("D2: Dashboard displays identical verdict word, date and 3 change chips", () => {
      render(
        <DashboardPage
          data={CANONICAL_DEMO_DATA}
          initialState="all-clear"
        />
      );

      expect(screen.getByText(/Not ready yet · Sat 31 Oct 2026/)).toBeInTheDocument();
      expect(screen.getByText("2 fixed")).toBeInTheDocument();
      expect(screen.getByText("1 still broken")).toBeInTheDocument();
      expect(screen.getByText("1 new")).toBeInTheDocument();
      expect(screen.getByText("Nothing needs you right now.")).toBeInTheDocument();
    });

    it("D3: Landing example Results pane matches verdict and reason identically", () => {
      render(<LandingPage data={CANONICAL_DEMO_DATA} />);

      const verdictWords = screen.getAllByText("Not ready yet");
      expect(verdictWords.length).toBeGreaterThanOrEqual(1);

      const reasons = screen.getAllByText(
        "People can browse, sign up and use discount codes, but paying fails for some — and one sign-up error never appears."
      );
      expect(reasons.length).toBeGreaterThanOrEqual(1);
    });

    it("D4: No step count asserted for Tom or Priya anywhere", () => {
      const { container } = render(<WatchLivePage data={CANONICAL_DEMO_DATA} />);
      const text = container.textContent || "";

      expect(text).not.toMatch(/Tom[^.]*?\b\d+\s+steps\b/i);
      expect(text).not.toMatch(/Priya[^.]*?\b\d+\s+steps\b/i);
      // Tom should have attempts, not steps
      expect(text).toContain("All 6 attempts · Done");
    });

    it("D5: P2 has Proof attached and no screenshot digit count", () => {
      render(<TestResultsPage data={CANONICAL_DEMO_DATA} />);

      expect(screen.getByText(/Proof attached · re-checked/)).toBeInTheDocument();
      expect(screen.queryByText(/\d+\s+screenshots · re-checked/i, {
        selector: "article:has(h3:contains('Sign-up error')) *",
      })).not.toBeInTheDocument();
    });

    it("D6: Previous test has no verdict word", () => {
      const { container } = render(
        <DashboardPage data={CANONICAL_DEMO_DATA} initialState="live-moment" />
      );
      const text = container.textContent || "";

      expect(text).toContain("Stopped early · 6 of 18 attempts");
      // Must not assert verdict word next to Wed 21 Oct 2026
      expect(text).not.toMatch(/Wed 21 Oct 2026[^.]*?Not ready yet/);
    });

    it("D7: Feelings quotes are verbatim and correctly attributed", () => {
      render(<TestResultsPage data={CANONICAL_DEMO_DATA} />);

      expect(
        screen.getByText(
          /The pay button just sat there\. I didn't know if I'd been charged\./
        )
      ).toBeInTheDocument();
      expect(
        screen.getByText(/MAYA · FIRST-TIME USER · BUY A T-SHIRT/)
      ).toBeInTheDocument();

      expect(
        screen.getByText(
          /Everything was fast — until the error that never appeared\./
        )
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          /TOM · EXPERT · SEE AN ERROR WHEN THE EMAIL IS ALREADY USED/
        )
      ).toBeInTheDocument();

      expect(
        screen.getByText(/It kept timing out on my connection\. I nearly left\./)
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          /PRIYA · IMPATIENT MOBILE USER · SEARCH FOR A T-SHIRT AND USE FILTERS/
        )
      ).toBeInTheDocument();
    });

    it("D8: Watch live shows Maya at step 5, Priya waiting 6 minutes, and no premature failure", () => {
      const { container } = render(<WatchLivePage data={CANONICAL_DEMO_DATA} />);
      const text = container.textContent || "";

      expect(text).toContain("At checkout — about to pay");
      expect(text).toContain("2 steps left");
      expect(text).toContain("Waiting 6 minutes");
      // Failure at step 6 must NOT be shown in Watch live
      expect(text).not.toContain("Clicked Pay — nothing happened");
      expect(text).not.toContain("Gave up and left");
    });
  });

  describe("Interactions & State Transitions (I1–I6)", () => {
    it("I1: MegaMenu opens on click, closes on Escape, and returns focus", async () => {
      const user = userEvent.setup();
      render(<MegaMenu />);

      const trigger = screen.getByRole("button", { name: /PRODUCT/i });
      expect(trigger).toHaveAttribute("aria-expanded", "false");

      await user.click(trigger);
      expect(trigger).toHaveAttribute("aria-expanded", "true");
      expect(screen.getAllByRole("menu")[0]).toBeInTheDocument();

      await user.keyboard("{Escape}");
      expect(trigger).toHaveAttribute("aria-expanded", "false");
      expect(trigger).toHaveFocus();
    });

    it("I3: StepList toggles between Show steps and Hide steps", async () => {
      const user = userEvent.setup();
      render(<StepList mode="watch-live-maya" />);

      const toggle = screen.getByRole("button", { name: "Show steps" });
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByText("Found a t-shirt")).not.toBeInTheDocument();

      await user.click(toggle);
      expect(toggle).toHaveTextContent("Hide steps");
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByText("Found a t-shirt")).toBeInTheDocument();

      await user.click(toggle);
      expect(toggle).toHaveTextContent("Show steps");
      expect(toggle).toHaveAttribute("aria-expanded", "false");
    });

    it("I4: TakeoverPanel transitions between State A and State B", async () => {
      const user = userEvent.setup();
      render(<TakeoverPanel testerName="Priya" taskName="Track an order" />);

      // State A: Idle
      expect(screen.getByText("Priya needs your help")).toBeInTheDocument();
      const takeOverBtn = screen.getByRole("button", {
        name: "Take over Priya's browser",
      });
      expect(takeOverBtn).toHaveAttribute("aria-pressed", "false");

      // Click -> State B
      await user.click(takeOverBtn);
      const titleB = screen.getByRole("heading", { name: "You are in control" });
      expect(titleB).toBeInTheDocument();
      const handBackBtn = screen.getByRole("button", {
        name: "Hand back to Priya",
      });
      expect(handBackBtn).toHaveAttribute("aria-pressed", "true");

      // Click -> Return to State A
      await user.click(handBackBtn);
      expect(screen.getByText("Priya needs your help")).toBeInTheDocument();
    });

    it("I5: UrlIntakeForm validates empty, unparseable and valid inputs without navigating", async () => {
      const user = userEvent.setup();
      let submittedOrigin = "";
      render(
        <UrlIntakeForm
          onValidSubmit={(origin) => {
            submittedOrigin = origin;
          }}
        />
      );

      const input = screen.getByPlaceholderText("yourapp.com");
      const button = screen.getByRole("button", { name: "START A TEST" });

      // Empty submit
      await user.click(button);
      expect(
        screen.getByText("Enter your app's address to start.")
      ).toBeInTheDocument();
      expect(input).toHaveAttribute("aria-invalid", "true");
      expect(submittedOrigin).toBe("");

      // Unparseable submit
      await user.type(input, "not a valid url !");
      await user.click(button);
      expect(
        screen.getByText(
          "That doesn't look like a web address. Check it and try again."
        )
      ).toBeInTheDocument();
      expect(submittedOrigin).toBe("");

      // Valid submit
      await user.clear(input);
      await user.type(input, "threadandco.example/shop?item=1");
      await user.click(button);
      expect(
        screen.getByText("We'll test https://threadandco.example")
      ).toBeInTheDocument();
      expect(submittedOrigin).toBe("https://threadandco.example");
    });
  });

  describe("Components & Accessibility (A1–A5, §10A)", () => {
    it("StatusPill renders symbol, word and tint", () => {
      const { rerender } = render(<StatusPill status="Worked" />);
      expect(screen.getByText("✓")).toBeInTheDocument();
      expect(screen.getByText("Worked")).toBeInTheDocument();

      rerender(<StatusPill status="Broken" />);
      expect(screen.getByText("✕")).toBeInTheDocument();
      expect(screen.getByText("Broken")).toBeInTheDocument();

      rerender(<StatusPill status="Could not check" />);
      expect(screen.getByText("?")).toBeInTheDocument();
      expect(screen.getByText("Could not check")).toBeInTheDocument();

      rerender(<StatusPill status="Not checked" />);
      expect(screen.getByText("–")).toBeInTheDocument();
      expect(screen.getByText("Not checked")).toBeInTheDocument();
    });

    it("CoverageBar carries proper aria-label and accessible image role", () => {
      render(<CoverageBar totals={CANONICAL_DEMO_DATA.totals} />);
      const barWrapper = screen.getByRole("img", {
        name: "11 of the 14 attempts we could check worked. 2 broken, 1 could not be checked, 4 not checked.",
      });
      expect(barWrapper).toBeInTheDocument();
    });

    it("NeedsYouRow renders attention symbol and action button", () => {
      render(
        <NeedsYouRow
          testerName="Priya"
          taskName="Track an order"
          waitingMinutes={6}
        />
      );
      expect(
        screen.getByText("Priya is stuck logging in — Track an order")
      ).toBeInTheDocument();
      expect(screen.getByText("Waiting 6 minutes")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Help Priya" })).toBeInTheDocument();
    });

    it("Footer includes normative bottom bar credit line", () => {
      render(<LandingPage data={CANONICAL_DEMO_DATA} />);
      expect(
        screen.getByText("© 2026 MarketTwin · Concept design")
      ).toBeInTheDocument();
      expect(screen.getByText("Developed by SJ")).toBeInTheDocument();
    });
  });
});

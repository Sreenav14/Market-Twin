/**
 * MarketTwin Arize-Inspired Concept Canonical Dataset (§4, §4B)
 * Used verbatim for demo mode and visual-regression fixtures.
 */

export interface ConceptApp {
  name: string;
  url: string;
}

export interface ConceptOwner {
  name: string;
  email: string;
}

export interface ConceptTester {
  id: string;
  name: string;
  label: "Expert" | "First-time user" | "Impatient mobile user";
  colour: string;
}

export interface ConceptVerdict {
  word: string;
  reason: string;
  honestInputs: string;
}

export interface ConceptTotals {
  attempts: number;
  checked: number;
  worked: number;
  broken: number;
  couldNotCheck: number;
  notChecked: number;
}

export type TaskStatusKey = "W" | "B" | "C" | "N";

export interface ConceptTask {
  n: number;
  name: string;
  tom: TaskStatusKey;
  maya: TaskStatusKey;
  priya: TaskStatusKey;
  notCheckedReason?: string;
  couldNotReason?: string;
}

export interface ConceptProof {
  screenshots: number | null;
  rechecked: boolean;
  chip: string;
}

export interface ConceptProblem {
  id: string;
  title: string;
  task: string;
  foundBy: "maya" | "tom" | "priya";
  description: string;
  proof: ConceptProof;
  failedStep?: number;
}

export interface ConceptSeenOnce {
  label: string;
  text: string;
  tester: string;
  task: number;
}

export interface ConceptFeeling {
  tester: "maya" | "tom" | "priya";
  task: string;
  quote: string;
}

export interface ConceptPreviousTest {
  dateLabel: string;
  status: string;
  verdict: string | null;
}

export interface ConceptChange {
  fixed: number;
  stillBroken: number;
  new: number;
}

export interface ConceptLiveSnapshot {
  startedMinutesAgo: number;
  testersFinished: number;
  attemptsDone: number;
  attemptsToGo: number;
  tom: {
    state: "finished";
    attemptsDone: number;
    attemptsTotal: number;
  };
  maya: {
    state: "doing";
    task: string;
    step: number;
    stepsTotal: number;
    activity: string;
    stepsLeft: number;
  };
  priya: {
    state: "needs-help";
    task: string;
    waitingMinutes: number;
    blockedAt: string;
  };
}

export interface ConceptPayload {
  app: ConceptApp;
  owner: ConceptOwner;
  testDate: string;
  testDateLabel: string;
  testers: ConceptTester[];
  verdict: ConceptVerdict;
  totals: ConceptTotals;
  headline: string;
  tasks: ConceptTask[];
  statusKey: Record<TaskStatusKey, string>;
  problems: ConceptProblem[];
  seenOnce: ConceptSeenOnce;
  mayaSteps: string[];
  feelings: ConceptFeeling[];
  previousTest: ConceptPreviousTest;
  change: ConceptChange;
  live: ConceptLiveSnapshot;
}

export const CANONICAL_DEMO_DATA: ConceptPayload = {
  app: { name: "Thread & Co.", url: "https://threadandco.example" },
  owner: { name: "Alex Morgan", email: "alex@threadandco.example" },
  testDate: "2026-10-31",
  testDateLabel: "Sat 31 Oct 2026",
  testers: [
    { id: "tom", name: "Tom", label: "Expert", colour: "#6842D6" },
    { id: "maya", name: "Maya", label: "First-time user", colour: "#0F766E" },
    { id: "priya", name: "Priya", label: "Impatient mobile user", colour: "#96521F" },
  ],
  verdict: {
    word: "Not ready yet",
    reason:
      "People can browse, sign up and use discount codes, but paying fails for some — and one sign-up error never appears.",
    honestInputs:
      "14 of 18 attempts checked · 3 testers · 2 problems confirmed · Sat 31 Oct 2026",
  },
  totals: {
    attempts: 18,
    checked: 14,
    worked: 11,
    broken: 2,
    couldNotCheck: 1,
    notChecked: 4,
  },
  headline: "11 of the 14 attempts we could check worked.",
  tasks: [
    { n: 1, name: "Buy a t-shirt", tom: "W", maya: "B", priya: "W" },
    { n: 2, name: "Create an account", tom: "W", maya: "W", priya: "W" },
    {
      n: 3,
      name: "See an error when the email is already used",
      tom: "N",
      maya: "B",
      priya: "N",
      notCheckedReason: "The plan gave this task to Maya only.",
    },
    {
      n: 4,
      name: "Search for a t-shirt and use filters",
      tom: "W",
      maya: "W",
      priya: "C",
      couldNotReason: "Search kept timing out on Priya's phone connection.",
    },
    { n: 5, name: "Apply a discount code", tom: "W", maya: "W", priya: "W" },
    {
      n: 6,
      name: "Track an order",
      tom: "N",
      maya: "N",
      priya: "W",
      notCheckedReason: "Needs a real order email, which the plan did not include.",
    },
  ],
  statusKey: {
    W: "Worked",
    B: "Broken",
    C: "Could not check",
    N: "Not checked",
  },
  problems: [
    {
      id: "P1",
      title: "Pay button does nothing",
      task: "Buy a t-shirt",
      foundBy: "maya",
      description:
        "When Maya tapped Pay, nothing happened. Tom and Priya paid without trouble.",
      proof: {
        screenshots: 7,
        rechecked: true,
        chip: "7 screenshots · re-checked ✓",
      },
      failedStep: 6,
    },
    {
      id: "P2",
      title: "Sign-up error is hidden",
      task: "See an error when the email is already used",
      foundBy: "maya",
      description: "The form gives no visible error when the email is already used.",
      proof: {
        screenshots: null,
        rechecked: true,
        chip: "Proof attached · re-checked ✓",
      },
    },
  ],
  seenOnce: {
    label: "Seen once — not counted",
    text: "Search suggestions flicker",
    tester: "tom",
    task: 4,
  },
  mayaSteps: [
    "Opened the store",
    "Found a t-shirt",
    "Chose size and colour",
    "Added it to her bag",
    "Went to checkout",
    "Clicked Pay — nothing happened",
    "Gave up and left",
  ],
  feelings: [
    {
      tester: "maya",
      task: "Buy a t-shirt",
      quote: "The pay button just sat there. I didn't know if I'd been charged.",
    },
    {
      tester: "tom",
      task: "See an error when the email is already used",
      quote: "Everything was fast — until the error that never appeared.",
    },
    {
      tester: "priya",
      task: "Search for a t-shirt and use filters",
      quote: "It kept timing out on my connection. I nearly left.",
    },
  ],
  previousTest: {
    dateLabel: "Wed 21 Oct 2026",
    status: "Stopped early · 6 of 18 attempts",
    verdict: null,
  },
  change: { fixed: 2, stillBroken: 1, new: 1 },
  live: {
    startedMinutesAgo: 21,
    testersFinished: 1,
    attemptsDone: 9,
    attemptsToGo: 9,
    tom: { state: "finished", attemptsDone: 6, attemptsTotal: 6 },
    maya: {
      state: "doing",
      task: "Buy a t-shirt",
      step: 5,
      stepsTotal: 7,
      activity: "At checkout — about to pay",
      stepsLeft: 2,
    },
    priya: {
      state: "needs-help",
      task: "Track an order",
      waitingMinutes: 6,
      blockedAt: "login",
    },
  },
};

/** Derive canonical headline sentence (§1 R1, §4) */
export function formatCoverageHeadline(checked: number, worked: number): string {
  return `${worked} of the ${checked} attempts we could check worked.`;
}

/** Derive coverage bar aria-label verbatim (§9, §10A.3) */
export function formatCoverageAriaLabel(totals: ConceptTotals): string {
  return `${totals.worked} of the ${totals.checked} attempts we could check worked. ${totals.broken} broken, ${totals.couldNotCheck} could not be checked, ${totals.notChecked} not checked.`;
}

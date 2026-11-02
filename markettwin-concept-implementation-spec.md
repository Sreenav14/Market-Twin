# MarketTwin — Arize-Inspired Concept: Complete Implementation Specification

**Audience:** an AI coding agent (Codex / Antigravity) implementing this design in the real MarketTwin repo (React + TypeScript frontend).
**Tone of this document:** imperative spec. Exact values everywhere. No ambiguity.

---

## §0 How to use this document

- Implement in order **§1 → §14** (the implementation order itself is §14).
- **§1 rules override anything conflicting later** in this document, and override anything conflicting in the existing codebase, older specs, or your own defaults.
- **Do not invent** copy, numbers, or components not specified here. If a value is not in this document, it does not get created — omit the claim or flag it under §16.
- Where the real app has pages beyond the 4 specified views (Landing page, Dashboard, Test results, Watch live), apply the §2 tokens, the §3 naming, and the §1 rules to them using the closest specified pattern.
- Anything marked **PROTOTYPE-ONLY** (§13) must **not** be built.

### Definition of Done — summary (read this first)

This work is DONE only when ALL of the following are true at the same time:

1. All 4 views are built: Landing page, Dashboard, Test results, Watch live — using §2/§2A/§2B/§2C tokens only, no other colours, fonts, or sizes.
2. Every number, quote, and string in the build matches §4 / §4A exactly when fed the §4 dataset. No invented numbers, quotes, trait labels, or step counts.
3. Every component in §10 / §10A exists once, is reused everywhere it appears, and matches its spec sheet (sizes, colours, states, aria).
4. Every interaction in §11 / §11A works with mouse, touch, and keyboard, and returns focus correctly.
5. Every test case in §15 / §15A passes. A single FAIL = not done.
6. Grep checks in §15 return ZERO for banned words, banned hexes, gradients, and glass effects.
7. No horizontal overflow at 360px, 390px, 768px, 1024px, 1440px.
8. The footer bottom bar reads exactly: left "© 2026 MarketTwin · Concept design", right "Developed by SJ" (see §6 item 11 and §2A footer tokens).
9. Nothing in §13 PROTOTYPE-ONLY was built, except the footer credit line in item 8 above, which IS built in production.
10. Backend, APIs, auth, and data model are unchanged except as allowed in §0A.

If any item cannot be met, STOP, do not improvise a substitute, and report the exact item number and blocker to the owner.

### §0A Repo scope — build here / do not touch

**BUILD / REPLACE (frontend only):**

- The 4 views: Landing page, Dashboard, Test results, Watch live — markup, styling, and their components (§10).
- Shared frontend tokens (CSS variables, §2A.1), base typography (§2B), header/nav/mega menu (§3), footer (§6 item 11).
- Frontend components listed in §10 only.

**KEEP UNCHANGED — DO NOT TOUCH:**

- Backend services, APIs, API routes, request/response shapes, and field names. Consume existing fields; never rename an API field to match UI wording.
- Auth / sign-in flow, session handling, billing, and any non-UI logic.
- Database schema, migrations, seed data logic (the §4 dataset is demo/sample data and visual-regression data only).
- Any page not listed above: restyle it ONLY with §2 tokens + §3 naming + §1 rules, using the closest §10 component. Do not redesign its layout or copy.

**ROUTES:**

- Do NOT create new routes except: Landing page, Dashboard, Test results, Watch live, plus routes that already exist in the repo for destinations named in §3 (Add an app flow, Your apps, Testers, Settings, Example report, How it works) if they already exist.
- Never link to a route that does not exist. If a §3 destination has no route, render its name as inert text (see §3) until the route exists.
- Do NOT use hash routing (`#landing`, `#dashboard`) in production — that was prototype-only (§13).

---

## §1 Non-negotiable rules

**R1 — One payload, one set of numbers.** Every count on every screen derives from the same test-result payload. Never hand-write a number in a component.

**R2 — Honesty.**
- A result may be labelled **Broken** only after it was checked again and failed again ("confirmed").
- "Could not check" is its own state — never merged into pass/fail.
- Feelings are shown as attributed quotes from a named tester, never as scores.
- Every aggregate shows its denominator: "11 of the 14 attempts we could check worked" — never "79% success".
- No naked numeric score, grade, or gauge anywhere.

**R3 — Colour means something or it is not there.** Colour is used ONLY for: (a) status, (b) tester identity (avatars/rings only), (c) the single flame accent on marketing surfaces. No decorative colour, no gradients, no glassmorphism, no blur/glow, no rainbow chart palettes. **Forbidden CSS:** `linear-gradient`, `radial-gradient`, `backdrop-filter` (except `none`), box-shadow glows.

**R4 — Plain words.** No jargon in UI copy. **Banned words in UI strings:** `deterministic`, `ledger`, `mission`/`missions`, `persona`/`personas`, `inconclusive`, `unverified`, "run" as a noun for a test (use "test"), `agent` (for testers — say "tester"). **Banned button labels:** Submit, OK, Click here, Learn more, Run a test.

**R5 — Buttons are verb-first and name the outcome:** "Start a test", "Add an app", "See test results", "Take over", "Hand back".

**R6 — One name per destination** (see §3 table). The same destination is never labelled two ways in the same surface type.

**R7 — Statuses are always colour + symbol + word together**, never colour alone.

**R8 — Restraint.** One dominant element per view; whitespace first, hairline dividers second, cards last; never nest cards; status is the only pill.

---

## §2 Design tokens (exact)

Light theme only — this direction has **NO dark mode**; do not invent one.

### Colours

| Token | Value | Use |
|---|---|---|
| `--paper` | `#FAF7F1` | Page canvas, marketing; workspace canvas is the same paper family |
| `--ink` | `#111111` | Primary text |
| `--ink-2` | `#5F5C52` | Secondary text, AA-verified |
| `--ink-faint` | `#6E6A5E` | Small/meta text, ≥ 5.35:1 — **never use `#777777` or lighter for text** |
| `--line` | `#E4E0D6` | Hairline borders/dividers |
| `--card` | `#FFFFFF` | Card surface |
| `--plum` | `#221244` | Announcement bar background (white text) |
| `--band-lilac` | `#E4E0F5` | Flat section background (one band per section max) |
| `--band-peach` | `#FCE8D8` | Flat section background |
| `--band-rose` | `#F9DEE4` | Flat section background |

### Accent — read carefully

| Token | Value | Rule |
|---|---|---|
| `--flame` | `#E4572E` | **Decorative only** (graphics, large shapes). White text on it measures 3.68:1 and **FAILS AA**. Never a text background, never a text colour for small text. |
| `--flame-deep` | `#BC4218` | All text-bearing flame: button fills, eyebrows, links, labels. White-on 5.34:1; on-paper 5.0:1. |

Primary marketing button = `--flame-deep` fill, white text, **0 radius**.

### Statuses (always symbol + word together, per R7)

| Status | Text colour | Tint | Symbol |
|---|---|---|---|
| Works | `#1F7A3D` | `#EAF6EE` | ✓ |
| Broken | `#C62F3B` | `#FDECEC` | ✕ |
| Could not check | `#8A5F00` | `#FFF4D6` | ? |
| Not checked | `#62625C` | `#F0EEE7` | – |
| Needs your help | ink text | — | ! (attention, not an error colour) |
| Doing / in-progress | — | — | ◐ |
| Finished | — | — | ✓ |

The Could-not-check amber `#8A5F00` is used for text, legend swatches **and** chart/bar segments — one amber everywhere.

### Tester identity

Avatars, initial chips and identity rings **only** — never text, never fills of large areas.

| Tester | Colour |
|---|---|
| Tom | `#6842D6` (violet) |
| Maya | `#0F766E` (teal) |
| Priya | `#96521F` (copper) |

New testers take the next colour from: `#1D64C8`, `#AE2F7D`, `#667A12`.

### Typography

| Role | Font |
|---|---|
| Display/headlines + the verdict word ONLY | `"Newsreader", Georgia, serif` |
| Body / UI / data | `"Inter", system-ui, sans-serif` — data is **never** serif |
| Labels, eyebrows, buttons, meta | `"IBM Plex Mono", monospace`, uppercase, letter-spacing `0.08em` |

Scale guidance: verdict word 40–56px serif; page H1 32–40px serif (marketing) / sans in workspace headers; section titles 20–24px; body 15–16px / 1.55; meta/labels 11–12px mono.

### Shape / spacing

- Buttons radius **0**; cards radius **10px** with 1px `--line` border and at most one soft shadow (`0 1px 2px rgba(17,17,17,.05)`).
- Page max width **1200px** marketing / fluid workspace with 24–32px gutters.
- Section vertical rhythm: 64–96px marketing, 24–40px workspace. Hairlines 1px.

### Breakpoints

- ≤ 900px: single column; mega menu becomes an accordion (see §7/§11).
- Verify **no horizontal overflow** at 360px, 390px, 768px, 1440px.

---

## §3 Naming system (exact)

### Canonical destination names

| Destination | The only name |
|---|---|
| Marketing home | "Landing page" |
| Signed-in home | "Dashboard" |
| One test's report | "Test results" |
| One test's live view | "Watch live" |

Inside a test, the tab strip is exactly: **"Test results | Watch live"**.

### Marketing header

Logo left. Top-level items: **PRODUCT ⌄** (the ONLY mega menu), **HOW IT WORKS**, **EXAMPLE REPORT**. Right: **SIGN IN** (text button; in the real app routes to the real sign-in) + **START A TEST** (primary).

**NO Pricing item anywhere** — the product has no pricing page. Never link to a destination that does not exist.

### Mega menu (PRODUCT)

Click-to-open disclosure (**NOT hover**). Three groups; each item = name + one-line description; **each destination exactly once**. After the audit fix there are **8 items** — the duplicate "Start a test" item was **REMOVED** (the header button covers it).

**Group "Start here":**

| Item | Description | Goes to |
|---|---|---|
| Add an app | "Give us your app's address. That is all we need to begin." | Landing start section; focuses the URL field |

**Group "See it working":**

| Item | Description |
|---|---|
| Dashboard | "Everything that needs you, and everything running." |
| Watch live | "See each tester working, as it happens." |
| Test results | "What worked, what broke, and the proof." |
| Testers | "Who checks your app, and how they see it." |

**Group "Get your answers":**

| Item | Description |
|---|---|
| Example report | "A real test, written the way yours will be." |
| How it works | "From address to answer, step by step." |
| Your apps | "Every app you have added, and its latest verdict." |

Implementer: if a listed real destination doesn't exist yet in the app, keep the item out until it does — never link to nothing.

### Workspace nav (signed-in)

**Dashboard · Needs your help · Your apps · Tests · Testers · Settings**

- **Badge rule:** the "Needs your help" count badge renders **ONLY** when ≥ 1 tester is actually blocked waiting (never in an all-clear state).
- **Active-state rule:** exactly one active item per view — Dashboard on Dashboard; **Tests on BOTH Test results and Watch live**; never two actives simultaneously.

### In-test context row (Test results & Watch live)

One slim row: **"THREAD & CO. · TEST · SAT 31 OCT 2026"** (app · TEST · date of test, mono) + the tab strip.

### Chrome rules

- Marketing header + announcement bar render **ONLY** on the landing page.
- Workspace views have exactly **ONE** header.
- Demo/sample data carries exactly **ONE** "Sample data" chip per workspace view.

---

## §4 Canonical demo dataset

Use **verbatim** for demo/sample mode and for visual regression tests. In production these values come from the API per R1.

- **App:** Thread & Co. (online t-shirt store, `https://threadandco.example`).
- **Workspace owner (fictional demo persona):** Alex Morgan, `alex@threadandco.example` — never use a real person's name/email in sample data.
- **Testers:** Tom — **Expert** — violet; Maya — **First-time user** — teal; Priya — **Impatient mobile user** — copper. These identity labels are the ONLY trait labels; do not introduce alternate trait systems like "Fast scanner".
- **Test:** Sat 31 Oct 2026 (a Saturday). 6 tasks × 3 testers = **18 attempts**.

### The grid (W = Worked, B = Broken, C = Could not check, N = Not checked)

| # | Task | Tom | Maya | Priya |
|---|---|---|---|---|
| 1 | Buy a t-shirt | W | B | W |
| 2 | Create an account | W | W | W |
| 3 | See an error when the email is already used | N | B | N |
| 4 | Search for a t-shirt and use filters | W | W | C |
| 5 | Apply a discount code | W | W | W |
| 6 | Track an order | N | N | W |

Reasons (verbatim):

- Task 3, Tom/Priya Not checked: "The plan gave this task to Maya only."
- Task 4, Priya Could not check: "Search kept timing out on Priya's phone connection."
- Task 6, Tom/Maya Not checked: "Needs a real order email, which the plan did not include."

### Totals (derive — never hardcode in markup)

Worked **11** · Broken **2** · Could not check **1** · Not checked **4** · checked = **14**.
Canonical sentence: **"11 of the 14 attempts we could check worked."**

### Verdict

- Word: **"Not ready yet"**
- Reason: "People can browse, sign up and use discount codes, but paying fails for some — and one sign-up error never appears."
- Honest-inputs strip (non-collapsible, always visible under the verdict): "14 of 18 attempts checked · 3 testers · 2 problems confirmed · Sat 31 Oct 2026"

### Problems (confirmed = failed again on re-check)

**P1 — "Pay button does nothing"**
- Task: Buy a t-shirt. Found by: Maya.
- Description: "When Maya tapped Pay, nothing happened. Tom and Priya paid without trouble."
- Proof: **7 screenshots, re-checked ✓**. Steps: Maya's canonical 7 (below); failure at step 6.

**P2 — "Sign-up error is hidden"**
- Task 3 (See an error when the email is already used). Found by: Maya.
- The form gives no visible error when the email is already used.
- Proof attached, re-checked ✓. **NO screenshot count is specified for P2 — do not invent one.**

**Seen once — NOT a confirmed problem** (label it "Seen once — not counted"): "Search suggestions flicker" (Tom, task 4).

### Maya's canonical step list for Buy a t-shirt

Use verbatim everywhere this attempt's steps appear:

1. Opened the store
2. Found a t-shirt
3. Chose size and colour
4. Added it to her bag
5. Went to checkout
6. Clicked Pay — nothing happened
7. Gave up and left

### Feelings (verbatim quotes, attribution fixed)

- Maya (Buy a t-shirt): "The pay button just sat there. I didn't know if I'd been charged."
- Tom (task 3): "Everything was fast — until the error that never appeared."
- Priya (Search): "It kept timing out on my connection. I nearly left."

### Previous test & change

- Previous test: **Wed 21 Oct 2026** — status "Stopped early · 6 of 18 attempts", **NO verdict** (do not show a verdict word for it).
- Change since previous test: **Fixed 2 · Still broken 1** (the sign-up error) **· New 1** (the pay button) — shown as three separate chips, never netted into one number.

### Live snapshot (Watch live + Dashboard live state)

- Test started **21 minutes ago**.
- Progress: "1 of 3 testers finished · 9 of 18 attempts done · 9 attempts to go".
- **Tom:** Finished, 6 of 6 attempts.
- **Maya:** Doing, Buy a t-shirt, **ON step 5 of 7** — "At checkout — about to pay". The step-6 failure must **NOT** be shown in live views.
- **Priya:** Needs your help — waiting **6 minutes**, blocked at login on task Track an order.
- The only time estimate anywhere in the product copy: **"about 20 minutes"** (for a full test).

---

## §5 Signature visual — "Three Looks, One Verdict"

Landing hero motif + a compact strip on Test results.

### Anatomy

Three panels side by side, each showing **THE SAME storefront** (Thread & Co. header, "Classic tee — $28", a Pay $28 button) rendered identically. Each panel is ringed at top with its tester's identity colour + avatar initial + name + identity label. Beneath each panel: that tester's outcome line (symbol + word) and ONE short line in their words.

| Panel | Outcome line | Their line |
|---|---|---|
| Tom | ✓ Worked — "Bought it with no trouble." | Small note: "Noticed: search suggestions flicker." |
| Maya | ✕ Broken — "Pay button does nothing." | "I didn't know if I'd been charged." |
| Priya — panel rendered **NARROWER** (a phone width) | ✓ Worked — "Bought it on her phone." | "? Search kept timing out — couldn't check it." |

### Strict rules

- **NO arrows. NO connecting lines. NO funnel/converge graphics between panels.** The testers are independent — that independence is the product's claim.
- Flat colours only (R3).

### "Put together" strip

Beneath the panels, one strip (label "PUT TOGETHER", mono) with three flat rows:

- "Works — Browsing, sign-up, discount codes"
- "Broken — Pay button (found by Maya, checked again)"
- "Couldn't check — Search, on Priya's phone"

…ending in an ink pill: **"Verdict · Not ready yet"**.

### Behaviour

- Animation: panels fade in together **once** on load. With `prefers-reduced-motion` they are simply static.
- The whole figure carries an `aria-label` summarising all three outcomes + the verdict.
- On ≤ 900px the panels stack vertically.
- The compact strip version on Test results sits directly under the verdict header and reuses the same component/data.

---

## §6 Landing page (section by section, in order)

**1. Announcement bar** (plum): "New — see a full example test, start to finish →" linking to Example report.

**2. Header** (per §3).

**3. Hero:**
- Eyebrow (mono, flame-deep text): "YOUR APP, TESTED LIKE A PERSON"
- H1 (serif): "Know if your app is ready — before your customers find out."
- Lede: "Give us your app's address. Three testers — an expert, a first-timer, and someone in a hurry on their phone — try to use it the way real people do. You get one honest answer, with proof: what worked, what broke, and what we could not check."
- Promise line: "We only call something broken when the evidence proves it — twice."
- Primary block — URL form: input placeholder "yourapp.com" + button "Start a test". Inline validation (**never navigate on bad input**):
  - Empty → "Enter your app's address to start."
  - Unparseable → "That doesn't look like a web address. Check it and try again."
  - Valid → echo back **ONLY** the parsed origin ("We'll test https://…"), with `aria-invalid` set/cleared appropriately.
- Beside/below the form: the segmented "three paths" control (a real tablist): "I have an app to test" / "Show me an example" / "How it works" — switching changes the hero's supporting panel, not the page.

**4. Signature visual** (§5) as the hero's product panel.

**5. Stat band** (boxless, serif numerals, honest numbers only): "18 attempts in a full test" / "3 testers, 3 viewpoints" / "2 problems confirmed in the example" / "0 scores you have to decode" — every figure traceable to §4.

**6. Example card** (the sample test as a tabbed mini-product; tabs are a WAI-ARIA tablist: "Test results | Watch live"):
- Test results pane = verdict word + reason, coverage bar (see §9 component), the two confirmed problems with proof chips, feelings quotes.
- Watch live pane = the three tester rows at the §4 live snapshot (Maya on step 5 — aligned with §8, no failure shown).

**7. How it works** (peach band, 3 steps in plain words):
- "1 Tell us the address — One address is enough. No setup, no scripts."
- "2 Testers try it for real — They click, type and pay like people do — and get stuck like people do."
- "3 You get one answer — Worked, broken, or could not check — each with the screenshots to prove it."

**8. What you get** (lilac band): the verdict anatomy — verdict word + reason + honest-inputs strip; the coverage bar; a problem row; a feelings quote — each annotated in one plain sentence.

**9. Feelings section:** the three §4 quotes as large serif pull-quotes with name + identity + task attribution.

**10. Final CTA** (rose band): serif headline "Find out before your customers do." + the URL form again + "A full test takes about 20 minutes."

**11. Footer:** background `--footer-deep` `#17102E` (see §2A); product columns using §3 names only; links to destinations that don't exist are rendered as inert text, never fake links; a short "How this page is designed" / Design-Notes block is **PROTOTYPE-ONLY** (do not build in production). The **bottom bar IS built in production**: left "© 2026 MarketTwin · Concept design", right "Developed by SJ" — mono 11px (style Meta/label, §2B), text white at 70% opacity on `#17102E`, 1px top hairline in white at 15% opacity, padding 16px 24px, left and right items on one row (stack left-over-right at <640px). No other text goes in the bottom bar.

---

## §7 Dashboard (attention-first; the signed-in home)

### Structure — max 5 sections, in this order

1. **Needs you** — admission rule: a row appears **ONLY** if a tester is blocked and cannot continue without the owner. Each row = tester avatar + name, what they're stuck on in plain words ("Priya is stuck logging in — Track an order"), waiting time ("Waiting 6 minutes"), one action button ("Help Priya").
2. **Happening now** — running tests with progress in words + bar ("Thread & Co. — testing now · Checked 9 of 18 attempts"); row click → Watch live.
3. **Your apps** — one card per app: name; latest verdict **IN WORDS** with its date ("Not ready yet · Sat 31 Oct 2026"); change chips vs the previous test ("2 fixed · 1 still broken · 1 new" — three chips, never netted); a per-test verdict strip (one segment per past test, coloured by that test's outcome state, with the stopped-early test shown as Not checked); action "See test results".
4. **Recent tests** — plain divider rows: app, date, status in words, attempts "x of 18".

### Forbidden on this page

KPI/stat card grids, delta percentages, charts, scores. (The data is sparse and categorical; numbers here would mislead.)

### Visual encodings allowed

Exactly two — **progress bars, verdict strips**.

### States

- **Live moment** (someone waiting + a test running): all sections as above.
- **All clear** (nothing blocked, nothing running): sections 1–2 are **REPLACED** by one calm line: "Nothing needs you right now." — no empty boxes, no zero cards. The app card then shows the finished verdict + delta chips.
- **Brand new** (no apps yet): the whole page is **ONE** empty state — serif headline "Your dashboard will live here." (this is the page's H1), one sentence, one primary button "Add an app".
- **Heading rule:** exactly one H1 per state.

---

## §8 Watch live

### Header block

Workspace header + context row (§3) + snapshot lines: "1 of 3 testers finished · 9 of 18 attempts done" and directly under it the plain-words remainder **"9 attempts to go."**

### Tester cards (one per tester, equal weight)

Each card: avatar (identity colour) + name + identity label; state line (symbol + word): "✓ Finished", "◐ Doing", "●/! Needs your help" (use "!" as the needs-help symbol consistently everywhere); current activity in words ("Buy a t-shirt — step 5 of 7 · At checkout — about to pay"); a plain-words progress line per tester **where canon supports it**:

- Maya: "2 steps left" — derived from her step position.
- Tom: "✓ All steps completed".
- Priya: **NO numeric progress claims** — her step totals are not defined; show her state only.

### Step lists

- Use a real browser-frame mock of the target app per card (the frame is a labelled picture of the app, never fake OS/browser chrome claims).
- Completed steps **COLLAPSE**: Maya's steps 1–4 render as one line "✓ Steps 1–4 · Done" with a toggle button "Show steps" / "Hide steps" (`aria-expanded`, `aria-controls`, ≥ 44px) revealing the canonical step names; current + upcoming steps stay visible.
- A fully finished tester's list collapses to one line: **"✓ All 6 attempts · Done"** for Tom — **attempts, NOT steps**. Only Maya's Buy attempt has a canonical step count of 7.

### Takeover

Inside the blocked tester's card — the **SAME component** is reused in the Dashboard Needs-you row. Panel states, exactly two:

- **(a)** "Priya needs your help — Log in to Priya's test browser to unblock Track an order." + button **"Take over Priya's browser"**.
- **(b)** After click: panel title **"You are in control"**, the frame becomes the owner's, button **"Hand back to Priya"** (`aria-pressed` toggles). Handing back restores state (a).

Priya's frame content shows the TARGET app's order-tracking login ("Track your order" / "Log in to see where your order is.") — **never a checkout login** (her checkout task already passed).

### Live honesty

- A live view **NEVER** shows a failure before it happens in the timeline. Maya's step-6 failure exists only in finished results.
- Waiting time counts up from the block start ("Waiting 6 minutes" at snapshot).

---

## §9 Test results

### Order

Context row + tabs (§3) → verdict block → Three-looks strip (§5 compact) → coverage → problems → feelings → what we did not check. The honest-inputs strip is attached to the verdict (always visible, non-collapsible).

### Verdict block

Verdict word (serif, **H1 of the view**) + reason sentence + honest-inputs strip (mono, small) — per §4.

### Coverage bar component

ONE horizontal stacked bar with exactly four segments in status colours (Works green, Broken red, Could not check `#8A5F00`, Not checked grey). Each segment labelled in words with its count in the legend beneath ("Worked 11 · Broken 2 · Could not check 1 · Not checked 4"). The bar itself carries a full worded `aria-label`: "11 of the 14 attempts we could check worked. 2 broken, 1 could not be checked, 4 not checked." Headline sentence above it: **"11 of the 14 attempts we could check worked."**

### Tasks × testers grid

Rows = 6 tasks, columns = 3 testers, each cell = status symbol + word. Not-checked cells show their reason on the row (per §4 reasons); the Could-not-check cell shows its reason inline.

### Comparison strip

"Since the last test (Wed 21 Oct 2026)" + three chips **Fixed 2 / Still broken 1 / New 1** (never netted).

### Problems list

Each problem = title, task, found-by (name + identity), description (§4 wording), proof chip, proof trail, steps (canonical list, failure step marked ✕ in Broken styling).

- **Proof chip format:** "7 screenshots · re-checked ✓" when a count exists (P1); "Proof attached · re-checked ✓" when it doesn't (P2) — never invent a count.
- **Proof trail component:** a row of 3 small flat screenshot thumbnails (bordered mini-panels, small step captions) + an overflow label "+4 more" **ONLY** when a total count exists (P1: 7 total, 3 shown, "+4 more"). The `aria-label` states the truth ("Screenshots from Maya's attempt (3 shown)" for P2; "7 screenshots, 3 shown" pattern for P1).

### Feelings section — "How it felt"

The three §4 quotes verbatim, each attributed name + identity + task.

### What we did not check

A plain list, one line per unchecked / couldn't-check group with its plain reason:

- "1 attempt could not be checked — Priya's search timed out on her connection."
- "Task 3 for Tom and Priya — the plan gave this task to Maya only."
- "Track an order for Tom and Maya — needs a real order email, which the plan did not include."

Plus the seen-once note: "Seen once, not counted as a problem: search suggestions flicker (Tom)."

---

## §10 Component inventory (build once, reuse)

`StatusPill` (symbol + word + tint), `VerdictBlock`, `CoverageBar`, `VerdictStrip` (per-test history), `ProofChip`, `ProofTrail`, `TesterCard`, `StepList` (with collapse), `TakeoverPanel`, `NeedsYouRow`, `ProgressLine` (words + bar), `MegaMenu`, `ContextTabs`, `UrlIntakeForm` (with the §6 validation states).

**No component outside this list without a spec change.**

---

## §11 Interactions & accessibility (all mandatory)

- **Mega menu:** button with `aria-haspopup` / `aria-expanded`; opens on **CLICK** (not hover); closes on **Esc** (focus returns to the control that opened it — including the mobile Menu button), on outside click, and on selection. ≤ 900px it becomes an accordion inside the mobile menu with identical names/order.
- **All switchers** (hero paths, example-card tabs, in-test tabs, any state switcher) are WAI-ARIA tablists: `role=tablist/tab/tabpanel`, roving tabindex, ArrowLeft/Right + Home/End keys, `aria-selected`.
- **Takeover + steps toggles:** real `<button>`s with `aria-pressed` / `aria-expanded` as applicable.
- **Targets:** every interactive element ≥ 44×44px (including tab strips — context tabs `min-height: 44px`).
- **Focus:** visible focus ring on every interactive element (2px ink outline, offset 2px); never `outline: none` without replacement.
- **Contrast** (measured; must re-verify after build): every text/background pair ≥ 4.5:1 (≥ 3:1 only for large display text). Known-good pairs: flame-deep on paper 5.0:1; white on flame-deep 5.34:1; `--ink-faint` on white 5.35:1; status texts 4.64–4.81:1; Not-checked `#62625C` 5.10:1. Known **FAILING** pair to avoid: white on `--flame` `#E4572E` (3.68:1) — flame bright is never a text background.
- **Motion:** `prefers-reduced-motion` disables the triptych fade and all non-essential animation. No scroll-jacking, no auto-rotating carousels, no count-up number animations anywhere.
- **Headings:** exactly one H1 per view/state; no skipped levels; the verdict word is the H1 on Test results.
- **Images/figures:** decorative motifs `aria-hidden`; meaningful figures get `role="img"` + a worded `aria-label` (coverage bars, cover bars, triptych).
- **Forms:** errors are inline, adjacent to the field, with `aria-invalid` and a described-by message; never fake-navigate on invalid input; echo only the parsed origin on success.

---

## §12 Patterns adopted from a component-library study (BoardUI) — structure only

- (a) Agent-progress expressed in plain words ("steps left" / "all steps completed") — §8.
- (b) Finished work collapses (task lists) — §8.
- (c) Evidence shown as a source trail with overflow — §9 ProofTrail.

**REJECTED from the same study (do not implement):** iridescent/glass loaders, gradient buttons/tiles, rainbow chart palettes, count-up animated metrics, delta-chip stat cards, fake browser frames, auto-rotating carousels, user-selectable accent colours.

---

## §13 Prototype-only — DO NOT BUILD

- The floating "Pages" prototype switcher.
- The dashboard demo-state switcher (in production the three dashboard states are **REAL** states driven by data, §7).
- "Sample data" chips (production shows them only when actually rendering sample/demo data).
- The footer "How this page is designed" / Design-Notes block. **Exception:** the footer bottom-bar credit line — left "© 2026 MarketTwin · Concept design", right "Developed by SJ" — is NOT prototype-only; build it in production exactly as specced in §6 item 11.
- Hash-based view switching (`#landing` etc. — production uses real routes).

---

## §14 Implementation order

1. Tokens + base components (§2, §10).
2. Naming pass across existing UI (§3) + banned-string cleanup.
3. Test results (§9) — the core value surface.
4. Watch live (§8), incl. `TakeoverPanel`.
5. Dashboard (§7) with real state logic.
6. Landing (§6), incl. signature visual (§5).
7. Accessibility verification pass (§11) against the checklist in §15.

---

## §15 Acceptance checklist (all must pass before calling it done)

**Data**
- [ ] Every rendered count equals the §4 totals when fed the §4 dataset.
- [ ] The sentence "11 of the 14 attempts we could check worked." appears exactly.
- [ ] Verdict word + reason match §4 on Landing example, Dashboard (all-clear) and Test results.
- [ ] Maya's step list is verbatim §4 in Results and (steps 1–5 portion) in Watch.
- [ ] The three feelings quotes are verbatim §4 with correct attribution.
- [ ] NO step count is asserted for Tom or Priya anywhere.
- [ ] P2 has no screenshot count.
- [ ] Previous test shows no verdict word.

**Strings** — grep must return **ZERO** in UI source:
- [ ] "Run a test" · "Submit" (as a button label) · "Click here" · "Learn more" · "deterministic" · "ledger" · "mission" · "persona" · "inconclusive" · "blocks checkout completely" · "#777777"

**Naming / nav**
- [ ] Mega menu items match §3 exactly (8 items, each destination once).
- [ ] Badge renders only when a tester is blocked.
- [ ] Exactly one active nav item per view; Tests active on both in-test views.

**Interactions** — probe each:
- [ ] Mega menu click / Esc (desktop trigger AND mobile Menu button refocus) / outside-click.
- [ ] All tablists keyboard-complete.
- [ ] Steps Show/Hide both ways.
- [ ] Takeover both ways.
- [ ] URL form empty / invalid / valid messages.

**A11y**
- [ ] All targets ≥ 44px (measure the tab strip).
- [ ] Contrast spot-checks per §11 pairs.
- [ ] One H1 per view/state.
- [ ] Reduced-motion disables the fade.
- [ ] No horizontal overflow at 360 / 390 / 768 / 1440.

**Visual**
- [ ] Zero `linear-gradient` / `backdrop-filter` in shipped CSS.
- [ ] Flame bright appears only in non-text graphics.
- [ ] Status colours match §2 hexes exactly, including the single `#8A5F00` amber in bars, legends and pills.

---

## §16 Open decisions (do not decide unilaterally; flag to the owner)

1. This spec implements the warm editorial (Arize-inspired) direction; a separate monochrome-ink direction exists — building this spec supersedes it for the covered surfaces.
2. The name "Dashboard" is retained per owner instruction (research suggested "Home").
3. No dark mode in this direction.
4. No pricing page exists in the product; if one is ever added, it enters §3's table first, then the header.

---

# EXPANSION ANNEX — Maximum-Detail Layers (§2A–§15A)

> Everything in this Annex is normative and has the same force as §1–§16. It ADDS detail; it does not replace or change any earlier value, copy, number, or rule. If the Annex and an earlier section ever appear to conflict on a value, the earlier section's value wins and the conflict must be reported to the owner — do not silently pick one. The ONLY intentional correction in this Annex is the footer bottom bar (§6 item 11, §13 exception, §2A footer tokens).

## §2A Complete colour reference

### §2A.1 Ready-to-paste CSS — paste verbatim, do not retype hexes

```css
:root{
  --paper:#FAF7F1; --card:#FFFFFF;
  --ink:#111111; --ink-2:#5F5C52; --ink-faint:#6E6A5E;
  --line:#E4E0D6;
  --plum:#221244; --footer-deep:#17102E;
  --band-lilac:#E4E0F5; --band-peach:#FCE8D8; --band-rose:#F9DEE4;
  --flame:#E4572E; --flame-deep:#BC4218; --flame-deep-hover:#A83A15;
  --works:#1F7A3D; --works-tint:#EAF6EE;
  --broken:#C62F3B; --broken-tint:#FDECEC;
  --couldnot:#8A5F00; --couldnot-tint:#FFF4D6;
  --notchecked:#62625C; --notchecked-tint:#F0EEE7;
  --tom:#6842D6; --maya:#0F766E; --priya:#96521F;
  --tester-4:#1D64C8; --tester-5:#AE2F7D; --tester-6:#667A12;
  --focus-ring:2px solid #111111; --focus-ring-dark:2px solid #FFFFFF;
  --shadow-soft:0 1px 2px rgba(17,17,17,.05);
  --shadow-panel:0 8px 24px rgba(17,17,17,.08);
}
```

Rules for the block above:

- Use ONLY these variables in component CSS. No raw hex anywhere else in the stylesheet, except `#FFFFFF`/`#000000` opacity overlays explicitly specced in this Annex.
- Do NOT add a dark-theme `:root`, a media-query theme, or extra variables. Light theme only.
- Do NOT rename variables. Components reference these names.

### §2A.2 Every token — Hex / RGB / HSL / used-for / never-used-for

| Token | Hex | RGB | HSL | Used for | NEVER used for |
|---|---|---|---|---|---|
| paper | `#FAF7F1` | 250,247,241 | 40°,43%,96% | Page canvas, all views | Text; card fills |
| card | `#FFFFFF` | 255,255,255 | 0°,0%,100% | Cards, mega-menu panel, inputs | Page canvas |
| ink | `#111111` | 17,17,17 | 0°,0%,7% | Primary text, H1–H3, primary workspace buttons, focus ring (light) | Large decorative fills except verdict pill + footer text rules below |
| ink-2 | `#5F5C52` | 95,92,82 | 46°,8%,35% | Secondary text, descriptions, captions | Headlines; status text; small text on tinted bands where it drops below 4.5:1 — use ink there |
| ink-faint | `#6E6A5E` | 110,106,94 | 47°,9%,40% | Meta, timestamps, footnotes ≥11px only | Body text; anything <11px; placeholder text alone |
| line | `#E4E0D6` | 228,224,214 | 43°,24%,87% | 1px hairlines, card borders, input borders | Text; focus rings; status colours |
| plum | `#221244` | 34,18,68 | 258°,58%,17% | Announcement bar background ONLY | Buttons; body sections; text |
| footer-deep | `#17102E` | 23,16,46 | 258°,48%,12% | Footer background ONLY | Any other section background |
| band-lilac | `#E4E0F5` | 228,224,245 | 252°,48%,92% | "What you get" section background, flat, whole section | Cards inside that section get `--card`, not lilac; text colour on it is ink only |
| band-peach | `#FCE8D8` | 252,232,216 | 27°,86%,92% | "How it works" section background, flat | Buttons; status tints |
| band-rose | `#F9DEE4` | 249,222,228 | 345°,64%,92% | Final CTA section background, flat | Error backgrounds (use broken tint) |
| flame | `#E4572E` | 228,87,46 | 14°,79%,54% | Graphics ONLY: large shapes, triptych graphic marks, decorative dots ≥24px | **Text, text backgrounds, buttons, links, icons <24px, borders carrying meaning** |
| flame-deep | `#BC4218` | 188,66,24 | 15°,77%,42% | ALL text-bearing flame: primary marketing buttons (white text on it), eyebrows, marketing links | Workspace primary buttons (those are ink); status |
| flame-deep-hover | `#A83A15` | 168,58,21 | 15°,78%,37% | Hover state of flame-deep buttons/links ONLY | Default state; focus state (focus adds ring, colour stays hover if hovered) |

### §2A.3 Status colours — text / tint / symbol (all three together, always, per R7)

| Status | Text hex / RGB / HSL | Tint hex / RGB | Symbol (exact character) | Used for | NEVER |
|---|---|---|---|---|---|
| Works | `#1F7A3D` / 31,122,61 / 141°,55%,30% | `#EAF6EE` / 234,246,238 | `✓` U+2713 | StatusPill text+icon, grid cells, coverage segment, legend swatch | Decorative green anywhere else |
| Broken | `#C62F3B` / 198,47,59 / 356°,59%,48% | `#FDECEC` / 253,236,236 | `✕` U+2715 | StatusPill, confirmed problems, error text in forms (see UrlIntakeForm) | Unconfirmed findings; warnings |
| Could not check | `#8A5F00` / 138,95,0 / 41°,100%,27% | `#FFF4D6` / 255,244,214 | `?` ASCII question mark in a pill/circle | StatusPill, coverage segment, legend, bar segment — THE SAME hex in all three | Any other amber/yellow anywhere |
| Not checked | `#62625C` / 98,98,92 / 60°,3%,37% | `#F0EEE7` / 240,238,231 | `–` en-dash U+2013 | StatusPill, grid cells, coverage segment | Disabled-button styling (disabled is ink at 40% + `aria-disabled`) |
| Needs your help | ink `#111111` text | no tint — white card + ink border emphasis | `!` ASCII exclamation in a circle | NeedsYouRow, TesterCard state line, nav badge | Red/error styling — this is attention, NOT an error |
| Doing / in-progress | ink `#111111` text | no tint | `◐` U+25D0 | TesterCard state line only | Spinners/loaders |
| Finished | ink `#111111` text + Works `✓` | no tint | `✓` | TesterCard, StepList collapsed line | — |

### §2A.4 Tester identity colours (avatars / rings / panel top edge ONLY)

| Tester | Hex | RGB | HSL | Where it may appear | NEVER |
|---|---|---|---|---|---|
| Tom | `#6842D6` | 104,66,214 | 258°,64%,55% | Tom avatar bg (white initial), 2px avatar border, 3px triptych panel top edge | Text, buttons, chart series |
| Maya | `#0F766E` | 15,118,110 | 175°,77%,26% | Same positions for Maya | Text (note: close to Works green — never rely on colour alone; name always adjacent) |
| Priya | `#96521F` | 150,82,31 | 26°,66%,35% | Same positions for Priya | Text |
| Tester 4 | `#1D64C8` | 29,100,200 | 214°,74%,45% | Only when a 4th tester exists in real data | Demo data (demo has exactly 3 testers) |
| Tester 5 | `#AE2F7D` | 174,47,125 | 325°,57%,43% | Only when a 5th tester exists | Demo data |
| Tester 6 | `#667A12` | 102,122,18 | 74°,74%,27% | Only when a 6th tester exists | Demo data |

Avatar construction: circle, background = tester colour, initial letter in white `#FFFFFF`, font Inter 600, size = 45% of avatar diameter. White on Tom/Maya/Priya colours is for the single initial ONLY (large, bold, non-essential — the name is always printed next to it in ink).

### §2A.5 Approved contrast pairings — the ONLY text/background pairs allowed

| Text | Background | Ratio | Verdict |
|---|---|---|---|
| ink `#111111` | paper `#FAF7F1` | ≥12:1 (approx. 15.6:1) | ✅ Approved, any size |
| ink `#111111` | card `#FFFFFF` | ≥12:1 | ✅ Approved, any size |
| ink `#111111` | band-lilac / band-peach / band-rose | ≥10:1 | ✅ Approved, any size |
| ink-2 `#5F5C52` | paper `#FAF7F1` | approx. 6.4:1 | ✅ Approved ≥12px |
| ink-2 `#5F5C52` | card `#FFFFFF` | approx. 6.9:1 | ✅ Approved ≥12px |
| ink-faint `#6E6A5E` | card `#FFFFFF` | 5.35:1 (measured) | ✅ Approved ≥11px only |
| ink-faint `#6E6A5E` | paper `#FAF7F1` | approx. 5.0:1 | ✅ Approved ≥11px only |
| white `#FFFFFF` | flame-deep `#BC4218` | 5.34:1 (measured) | ✅ Approved — primary marketing button |
| flame-deep `#BC4218` | paper `#FAF7F1` | 5.0:1 (measured) | ✅ Approved — eyebrows, links |
| white `#FFFFFF` | plum `#221244` | ≥12:1 | ✅ Announcement bar |
| white 70% on footer-deep | footer-deep `#17102E` | ≥7:1 for 11px mono footer bar | ✅ Footer bottom bar + footer body text only |
| Works `#1F7A3D` | works tint `#EAF6EE` / white | 4.64–4.81:1 range (measured family) | ✅ Status text ≥12px, always with symbol+word |
| Broken `#C62F3B` | broken tint `#FDECEC` / white | 4.64–4.81:1 range | ✅ Status text ≥12px, always with symbol+word |
| Could-not `#8A5F00` | couldnot tint `#FFF4D6` / white | 4.64–4.81:1 range | ✅ Status text ≥12px, always with symbol+word |
| Not-checked `#62625C` | notchecked tint `#F0EEE7` / white | 5.10:1 (measured) | ✅ Status text ≥12px |
| white `#FFFFFF` | flame `#E4572E` | **3.68:1** | ❌ **FORBIDDEN — never ship this pairing** |
| flame `#E4572E` | paper / white (as text) | <4.5:1 | ❌ FORBIDDEN as text |
| `#777777` or lighter grey | anything (as text) | <4.5:1 | ❌ FORBIDDEN — token does not exist |
| ink-2 / ink-faint | band tints | varies, may drop <4.5:1 | ❌ Use ink on bands |

**Focus ring:** light surfaces `outline:2px solid #111111; outline-offset:2px`; dark surfaces (plum bar, footer-deep, ink buttons) `outline:2px solid #FFFFFF; outline-offset:2px`. Never remove the outline without this replacement. Never use flame for the focus ring.

## §2B Full type scale — use ONLY these styles

Notation: size/line-height in px. Every text element in the build maps to exactly ONE row. If text does not fit a row, the text is wrong — shorten the copy (using §4A strings), do not invent a new style.

| Style name | Font | Size/LH | Weight | Letter-spacing | Used for | Never for |
|---|---|---|---|---|---|---|
| Display | Newsreader, Georgia, serif | 56/64 desktop; 40/46 at <900px | 500 | -0.01em | Landing H1 ONLY (1 per landing page) | Workspace; data |
| H1-workspace | Inter, system-ui, sans-serif | 28/36 | 650 | 0 | Dashboard H1, Watch H1, page titles in workspace | Marketing hero |
| Verdict-word | Newsreader, Georgia, serif | 48/52 desktop; 36/40 mobile | 550 | -0.01em | The verdict word ONLY, e.g. "Not ready yet" | Any other headline |
| H2-marketing | Newsreader, Georgia, serif | 32/40 | 500 | -0.005em | Landing section titles | Workspace section headers |
| H2-workspace | Inter | 22/30 | 650 | 0 | Workspace section headers: "Needs you", "Happening now", "Your apps", "Recent tests" | Marketing |
| H3 | Inter | 18/26 | 600 | 0 | Card titles, problem titles, tester names in cards | Body copy |
| Body | Inter | 16/26 | 400 | 0 | Paragraphs, ledes, descriptions; max line length 68 characters | Labels; tables |
| Body-small | Inter | 14/22 | 400 | 0 | Secondary paragraphs, problem descriptions, grid explanations | Primary lede |
| Meta/label | IBM Plex Mono, monospace | 11/16 | 500 | 0.08em, UPPERCASE | Eyebrows, context row, honest-inputs strip, footer bar, group labels, captions | Body paragraphs; sentences longer than ~8 words |
| Button-label | IBM Plex Mono, monospace | 13/16 | 600 | 0.06em, UPPERCASE | ALL button text | Links inside paragraphs (those are Body, underlined) |
| Quote | Newsreader, serif, italic | 22/32 | 500 | 0 | Feelings pull-quotes ONLY, with attribution in Meta/label + Body-small | Verdict; headlines |
| Stat-numeral | Newsreader, serif | 40/44 | 500 | 0 | Stat band figures ONLY ("18", "3", "2", "0") | Scores/gauges — none exist; any other number |
| Grid-cell | Inter | 14/20 | 400 (status word 600) | 0 | Tasks×testers grid, tables, Recent tests rows | Headlines |
| Mono-data | IBM Plex Mono, monospace | 12/18 | 400 | 0.02em | Dates in context rows, counts in strips where mono is specced, "+4 more" | Body paragraphs |

**Hard rules (restated, testable):**

- Serif (Newsreader) NEVER appears in: data, tables, grids, labels, buttons, status pills, forms.
- Mono (IBM Plex Mono) NEVER appears in: body paragraphs, quotes, problem descriptions.
- Inter is the default. When in doubt, the style is Body or Body-small in Inter.
- Weights allowed: Inter 400/600/650; Newsreader 500/550; Mono 400/500/600. No 700+ bold anywhere. No italics except Quote style.
- Text alignment: left everywhere. Centre ONLY: triptych verdict pill text, stat band figure+caption pairs, brand-new empty state.

## §2C Spacing, layout, and component dimensions

### §2C.1 Spacing scale — the ONLY spacing values allowed

`4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48 · 64 · 96` px. No 6px, 10px, 14px, 18px, 28px, etc. in margins/padding/gaps (font line-heights in §2B are exempt).

| Value | When to use |
|---|---|
| 4px | Icon-to-symbol gap inside a pill; tight inline gaps |
| 8px | Gap between pill and its label; gap inside compact rows; grid cell vertical padding |
| 12px | Gap between avatar and name; form label-to-input gap; list item gap |
| 16px | Card inner gap between blocks; mobile page gutter; footer bar vertical padding |
| 20px | Default card padding (all sides) |
| 24px | Verdict block padding; marketing page side padding; gap between cards in a row |
| 32px | Workspace section gap; workspace desktop gutter; gap between tester cards |
| 40px | Gap between major blocks inside a marketing section |
| 48px | Hero inner spacing; empty-state padding |
| 64px | Minimum marketing section top/bottom padding |
| 96px | Maximum marketing section top/bottom padding (hero + final CTA only) |

### §2C.2 Fixed dimensions — measure these in the built UI (§15A)

| Element | Exact value |
|---|---|
| Marketing container | max-width 1200px, centred, side padding 24px (16px at ≤640px) |
| Workspace container | max-width none (fluid), gutters 32px desktop / 16px at ≤900px |
| Announcement bar | height 36px, plum bg, white Meta/label text centred |
| Marketing header | height 64px, paper bg, 1px line bottom border |
| Workspace header | height 56px, card bg, 1px line bottom border |
| Context row (in-test) | height 44px, Meta/label text, 1px line bottom border |
| Marketing section gap | 88px vertical padding target (allowed range 64–96px, pick 88px unless §6 walkthrough says otherwise) |
| Workspace section gap | 32px between sections |
| Card | radius 10px, border 1px `--line`, bg `--card`, padding 20px, shadow `--shadow-soft` max |
| Verdict block | padding 24px, radius 10px |
| Button | padding 12px 20px, min-height 44px, radius 0, style Button-label |
| Input (URL) | height 48px, padding 0 16px, radius 0, border 1px `--line`, Body style |
| Avatar | 32px in cards, 24px inline in rows, 40px in triptych panel headers; circle |
| Identity ring | panel top edge: 3px solid tester colour; avatar border: 2px solid tester colour |
| Hairline | 1px solid `--line` everywhere; never 2px dividers except tab underline + identity edge |
| Coverage bar | height 14px, radius 7px, segments butt-joined, no gaps |
| Verdict strip segment | height 8px, radius 4px, gap 4px between segments |
| Proof thumbnail | 56×36px, radius 6px, border 1px `--line`, bg paper |
| Mega-menu panel | max-width 880px, radius 12px, bg card, border 1px `--line`, shadow `--shadow-panel`, padding 24px |
| Status pill | min-height 24px, padding 4px 12px, radius 999px (pill is the ONLY fully-rounded element besides avatars/bars) |
| Tab (ContextTabs) | min-height 44px, padding 12px 16px |

### §2C.3 Breakpoints — what changes, exactly

| Range | Layout rules |
|---|---|
| ≥1200px | Marketing container 1200px centred. Triptych: 3 columns (Priya panel at phone width ≈ 260px, others flexible equal). Mega menu: full 880px panel, 3 columns. Tester cards: 3 in a row. Tasks grid: full table. |
| 900–1199px | Marketing container fluid with 24px padding. Triptych: 3 columns, narrower gaps (16px). Tester cards: 3 in a row if ≥1024px, otherwise stack (see below). Mega menu: panel width = viewport − 48px, still 3 columns down to 901px. |
| 640–899px | Mega menu CLOSED as panel; navigation becomes mobile menu with accordion groups (same names/order, §11). Triptych stacks vertically, Priya panel centred at 260px width. Tester cards stack 1 per row. Dashboard sections stack. Coverage legend wraps to 2 rows. Display type drops to 40/46. |
| <640px | Page padding 16px. All grids single-column. Stat band: 2×2 grid. Footer columns stack; footer bottom bar stacks (left line, then "Developed by SJ" below it, both left-aligned). Buttons in forms go full-width under the input (URL form stacks: input row 1, button row 2). H1-workspace 24/32. Verdict-word 36/40. NO horizontal scroll at 360px — test it (§15A). |

### §2C.4 ASCII wireframes — section order and proportions are normative

Landing page (desktop, proportions approximate, order exact):

```
+--------------------------------------------------------------+
| ANNOUNCEMENT BAR 36px  plum                                  |
+--------------------------------------------------------------+
| HEADER 64px  logo | PRODUCT v  HOW IT WORKS  EXAMPLE REPORT |
|                                   SIGN IN   [START A TEST]   |
+--------------------------------------------------------------+
| HERO  eyebrow / H1 (Display) / lede / promise                |
|       [ URL input 48px          ][ START A TEST ]            |
|       validation message line (reserved, 22px min-height)    |
|       segmented control: 3 tabs                              |
+--------------------------- triptych -------------------------+
| [Tom panel] [Maya panel] [Priya panel - narrow]              |
| PUT TOGETHER strip + [Verdict - Not ready yet] pill          |
+--------------------------------------------------------------+
| STAT BAND  18 / 3 / 2 / 0  (4 figures, no box)               |
| EXAMPLE CARD  tabs: Test results | Watch live                |
| HOW IT WORKS  peach band, 3 steps                            |
| WHAT YOU GET  lilac band, verdict anatomy                    |
| FEELINGS  3 serif pull-quotes                                |
| FINAL CTA  rose band, H2 + URL form                          |
+--------------------------------------------------------------+
| FOOTER  footer-deep: columns, then bottom bar                |
| (c) 2026 MarketTwin - Concept design      Developed by SJ    |
+--------------------------------------------------------------+
```

Dashboard / Watch live / Test results wireframes:

```
DASHBOARD                          WATCH LIVE
+----------------------------+     +----------------------------+
| WORKSPACE HEADER 56px      |     | WORKSPACE HEADER 56px      |
| H1 Dashboard               |     | CONTEXT ROW 44px           |
| NEEDS YOU (live only)      |     | tabs Test results|Watch    |
|  [NeedsYouRow x n]         |     | H1 + snapshot lines        |
| HAPPENING NOW              |     | "9 attempts to go."        |
|  [ProgressLine rows]       |     | [Tom card][Maya][Priya]    |
| YOUR APPS                  |     |  Priya card contains       |
|  [app card: verdict words, |     |  TakeoverPanel             |
|   3 change chips, strip]   |     +----------------------------+
| RECENT TESTS (rows)        |
+----------------------------+     TEST RESULTS
                                   +----------------------------+
ALL-CLEAR: Needs you + Happening | WORKSPACE HEADER + CONTEXT |
now REPLACED by 1 calm line.     | tabs                       |
BRAND-NEW: H1 + 1 sentence +     | VERDICT BLOCK (H1 = word)  |
[Add an app] only.               | honest-inputs strip        |
                                   | THREE-LOOKS STRIP (compact)|
                                   | COVERAGE bar + legend      |
                                   | TASKS x TESTERS GRID       |
                                   | SINCE LAST TEST chips      |
                                   | PROBLEMS P1, P2 (+trails)  |
                                   | HOW IT FELT (3 quotes)     |
                                   | WHAT WE DID NOT CHECK list |
                                   +----------------------------+
```

## §3A Naming — worked examples and anti-examples

Correct (copy these patterns):

- ✅ Header button: "START A TEST" → starts a test. Nav item: "Test results" → the report. Tab: "Watch live" → live view. Badge: "Needs your help" + count only when blocked.
- ✅ Row action: "Help Priya" (verb + person). Card action: "See test results". Takeover: "Take over Priya's browser" → "Hand back to Priya".

Wrong (never ship these — each was a real drift failure):

- ❌ "Run a test" / "Run test" / "Start test run" — banned phrase, wrong noun.
- ❌ "Reports", "Results page", "Test report", "Live view", "Live test" for the two in-test destinations — the ONLY names are "Test results" and "Watch live".
- ❌ "Agents", "Personas", "Bots" for Tom/Maya/Priya — they are "testers" everywhere, including aria-labels and alt text.
- ❌ "Submit", "OK", "Continue" (alone), "Click here", "Learn more" as any button/link label.
- ❌ Invented trait labels: "Fast scanner", "Careful shopper", "Bargain hunter" — ONLY "Expert", "First-time user", "Impatient mobile user" (§4).
- ❌ "Homepage" for Dashboard, "Overview" for Dashboard, "Home" in workspace nav (owner decision §16.2 keeps "Dashboard").

Reuse-vs-new decision table:

| Situation | Decision |
|---|---|
| Element appears in §10 list | REUSE that component. Never build a second version. |
| Same visual, different data (e.g. NeedsYouRow on Dashboard + Watch) | REUSE one component with props. Never copy-paste markup. |
| New page beyond the 4 views needs a card/row/pill | REUSE closest §10 component + §2 tokens. |
| Genuinely new element not covered | STOP. Add nothing. Flag to owner under §16 process. |
| Existing repo component conflicts with §10 spec sheet | CHANGE the existing component to match §10A; do not keep both. |

## §4B Canonical dataset as JSON — copy-paste, do not retype values

Use this object verbatim for demo/sample mode and visual-regression fixtures. In production, the API supplies the same shape; components read ONLY from this shape (R1).

```json
{
  "app": {"name": "Thread & Co.", "url": "https://threadandco.example"},
  "owner": {"name": "Alex Morgan", "email": "alex@threadandco.example"},
  "testDate": "2026-10-31",
  "testDateLabel": "Sat 31 Oct 2026",
  "testers": [
    {"id": "tom", "name": "Tom", "label": "Expert", "colour": "#6842D6"},
    {"id": "maya", "name": "Maya", "label": "First-time user", "colour": "#0F766E"},
    {"id": "priya", "name": "Priya", "label": "Impatient mobile user", "colour": "#96521F"}
  ],
  "verdict": {
    "word": "Not ready yet",
    "reason": "People can browse, sign up and use discount codes, but paying fails for some — and one sign-up error never appears.",
    "honestInputs": "14 of 18 attempts checked · 3 testers · 2 problems confirmed · Sat 31 Oct 2026"
  },
  "totals": {"attempts": 18, "checked": 14, "worked": 11, "broken": 2, "couldNotCheck": 1, "notChecked": 4},
  "headline": "11 of the 14 attempts we could check worked."
}
```

```json
{
  "tasks": [
    {"n": 1, "name": "Buy a t-shirt", "tom": "W", "maya": "B", "priya": "W"},
    {"n": 2, "name": "Create an account", "tom": "W", "maya": "W", "priya": "W"},
    {"n": 3, "name": "See an error when the email is already used", "tom": "N", "maya": "B", "priya": "N",
     "notCheckedReason": "The plan gave this task to Maya only."},
    {"n": 4, "name": "Search for a t-shirt and use filters", "tom": "W", "maya": "W", "priya": "C",
     "couldNotReason": "Search kept timing out on Priya's phone connection."},
    {"n": 5, "name": "Apply a discount code", "tom": "W", "maya": "W", "priya": "W"},
    {"n": 6, "name": "Track an order", "tom": "N", "maya": "N", "priya": "W",
     "notCheckedReason": "Needs a real order email, which the plan did not include."}
  ],
  "statusKey": {"W": "Worked", "B": "Broken", "C": "Could not check", "N": "Not checked"}
}
```
```json
{
  "problems": [
    {"id": "P1", "title": "Pay button does nothing", "task": "Buy a t-shirt",
     "foundBy": "maya",
     "description": "When Maya tapped Pay, nothing happened. Tom and Priya paid without trouble.",
     "proof": {"screenshots": 7, "rechecked": true, "chip": "7 screenshots · re-checked ✓"},
     "failedStep": 6},
    {"id": "P2", "title": "Sign-up error is hidden",
     "task": "See an error when the email is already used", "foundBy": "maya",
     "description": "The form gives no visible error when the email is already used.",
     "proof": {"screenshots": null, "rechecked": true, "chip": "Proof attached · re-checked ✓"}}
  ],
  "seenOnce": {"label": "Seen once — not counted", "text": "Search suggestions flicker", "tester": "tom", "task": 4},
  "mayaSteps": ["Opened the store", "Found a t-shirt", "Chose size and colour", "Added it to her bag", "Went to checkout", "Clicked Pay — nothing happened", "Gave up and left"],
  "feelings": [
    {"tester": "maya", "task": "Buy a t-shirt", "quote": "The pay button just sat there. I didn't know if I'd been charged."},
    {"tester": "tom", "task": "See an error when the email is already used", "quote": "Everything was fast — until the error that never appeared."},
    {"tester": "priya", "task": "Search for a t-shirt and use filters", "quote": "It kept timing out on my connection. I nearly left."}
  ],
  "previousTest": {"dateLabel": "Wed 21 Oct 2026", "status": "Stopped early · 6 of 18 attempts", "verdict": null},
  "change": {"fixed": 2, "stillBroken": 1, "new": 1},
  "live": {"startedMinutesAgo": 21, "testersFinished": 1, "attemptsDone": 9, "attemptsToGo": 9,
    "tom": {"state": "finished", "attemptsDone": 6, "attemptsTotal": 6},
    "maya": {"state": "doing", "task": "Buy a t-shirt", "step": 5, "stepsTotal": 7, "activity": "At checkout — about to pay", "stepsLeft": 2},
    "priya": {"state": "needs-help", "task": "Track an order", "waitingMinutes": 6, "blockedAt": "login"}}
}
```

NOTE on `mayaSteps`: §4's verbatim list is authoritative. NEVER edit a step's wording to "improve" it — step 3 is "Chose size and colour", step 6 is "Clicked Pay — nothing happened".

Data-source rule for every component: props come from this payload shape ONLY. A component must never contain a literal count, date, quote, or step string in its markup — if a string is in the component file, it is a bug (exception: fixed UI labels from §4A, e.g. button labels, section headers).

## §10A Component spec sheets — build exactly these, once each

Common rules for ALL components: spacing only from §2C.1; colours only from §2A.1; type only from §2B; states: hover changes ONLY the part stated, focus-visible ALWAYS adds the §2A.5 focus ring and changes nothing else, disabled = ink at 40% opacity + `aria-disabled="true"` + no hover/pointer events (never grey `#777`-family). A component must NOT: fetch its own data, hardcode counts, render a second component's job, or add decorative elements.

### 10A.1 StatusPill

- **Purpose:** show ONE status as symbol + word + tint, everywhere a status appears outside the grid.
- **Anatomy (in order):** [symbol span] 4px gap [word span].
- **Sizes:** min-height 24px; padding 4px 12px; radius 999px; symbol 12px; word: Grid-cell style, weight 600, 13px/18px.
- **Colours:** bg = status tint; text+symbol = status text hex (§2A.3). Example — Works: bg `#EAF6EE`, text `#1F7A3D`, content "✓ Worked". Broken: bg `#FDECEC`, text `#C62F3B`, "✕ Broken". Could not check: bg `#FFF4D6`, text `#8A5F00`, "? Could not check". Not checked: bg `#F0EEE7`, text `#62625C`, "– Not checked".
- **States:** default only (non-interactive). If wrapped in a link/button, the WRAPPER carries hover/focus; the pill itself never changes.
- **Spacing:** 8px gap to adjacent label text; never stack two pills touching — 8px gap minimum.
- **Responsive:** never shrinks, never abbreviates the word ("Could not check" stays full at 360px; wrap the row instead).
- **Aria:** plain text is sufficient (symbol is decorative: `aria-hidden="true"` on symbol span, word carries meaning). Never colour-only.
- **Must NOT do:** show a status without its word; show "Broken" for unconfirmed findings; be used as a button/chip/filter.

### 10A.2 VerdictBlock (includes honest-inputs strip)

- **Purpose:** the single dominant element of Test results; also reused (compact) in Landing example card and Dashboard app card verdict line.
- **Anatomy:** [Meta/label eyebrow "VERDICT"] 8px [verdict word] 12px [reason, Body] 16px [honest-inputs strip: 1px line top border, padding-top 12px, Meta/label ink-2, always visible, NEVER collapsible].
- **Sizes:** block padding 24px; bg card; border 1px line; radius 10px. Verdict word: Verdict-word style, ink. Filled example: word "Not ready yet", reason "People can browse, sign up and use discount codes, but paying fails for some — and one sign-up error never appears.", strip "14 OF 18 ATTEMPTS CHECKED · 3 TESTERS · 2 PROBLEMS CONFIRMED · SAT 31 OCT 2026" (rendered uppercase by the Meta/label style — store the §4 string as-is, CSS does the casing).
- **States:** non-interactive; no hover. Compact variant: word at H2-workspace serif equivalent 32/40, strip omitted ONLY on Dashboard app cards (verdict word + date instead); strip is MANDATORY on Test results and Landing example.
- **Responsive:** <640px word 36/40; strip wraps to 2 lines, never truncates, never hides.
- **Aria:** verdict word is the page H1 on Test results (`<h1>`). Strip is a `<p>`, never hidden behind a toggle.
- **Must NOT do:** show a score/gauge/percentage; hide the strip; show a verdict for the previous (stopped-early) test.

### 10A.3 CoverageBar

- **Purpose:** show the 4-way split of all attempts in one bar + worded legend.
- **Anatomy:** [headline sentence, Body, weight 600] 12px [bar: 4 segments left-to-right in this order: Worked, Broken, Could not check, Not checked] 12px [legend: 4 items in same order, each = 12×12px swatch radius 3px + symbol + word + count].
- **Sizes/colours:** bar height 14px, radius 7px, width 100%; segment widths proportional to counts (demo: 11/18, 2/18, 1/18, 4/18 of full width — note denominator for WIDTH is all 18 attempts; the headline sentence uses checked=14). Segment colours: Worked `#1F7A3D` (solid status colour, not tint), Broken `#C62F3B`, Could not check `#8A5F00`, Not checked `#62625C`. No gaps, no borders between segments, no labels inside segments.
- **Filled example:** headline "11 of the 14 attempts we could check worked." Legend: "✓ Worked 11 · ✕ Broken 2 · ? Could not check 1 · – Not checked 4".
- **States:** non-interactive. No hover tooltips (all information is already visible as text).
- **Responsive:** bar stays full-width at all sizes; legend wraps (2×2 at <640px); headline never truncates.
- **Aria:** wrapper `role="img"`, `aria-label="11 of the 14 attempts we could check worked. 2 broken, 1 could not be checked, 4 not checked."` (exact §9 string); inner bar `aria-hidden="true"`.
- **Must NOT do:** use tints for segments; reorder segments; show percentages; animate width on scroll.

### 10A.4 VerdictStrip

- **Purpose:** one app's test history at a glance on Dashboard "Your apps" cards.
- **Anatomy:** horizontal row of segments, oldest left → newest right, one segment per past test.
- **Sizes/colours:** segment height 8px, radius 4px, width flexible equal, gap 4px. Segment colour = that test's outcome state colour (§2A.3 solid): a test whose verdict exists uses ink `#111111` if "Not ready yet"-family is not a status — RULE: segment colour mapping is: finished test = ink; stopped-early / not-checked test = Not-checked `#62625C` at tint strength i.e. bg `#F0EEE7` with 1px line border. Do NOT invent green/red per-test verdict colours — verdicts are words, not statuses.
- **Filled example (Thread & Co.):** 2 segments: [stopped-early segment, pale] [latest finished test, ink], with caption in Body-small ink-2: "Last test: Sat 31 Oct 2026".
- **States:** non-interactive in V1; if a segment later becomes a link, the whole strip gets one link per segment with `aria-label="Test, Sat 31 Oct 2026, Not ready yet"` — do not build links in V1.
- **Responsive:** never wraps; segments shrink equally; minimum segment width 16px, then oldest segments drop with a "+n earlier" Meta/label note.
- **Aria:** `role="img"`, `aria-label` listing each test date + verdict word or "Stopped early, no verdict".
- **Must NOT do:** encode scores; use status green/red; show a verdict segment for the stopped-early test in ink.

### 10A.5 ProofChip

- **Purpose:** one-line proof statement under a problem description.
- **Anatomy:** [Meta/label text in ink-2] — no pill, no bg, no border.
- **Exact patterns:** with count: `"{n} screenshots · re-checked ✓"` → P1: "7 screenshots · re-checked ✓". Without count: `"Proof attached · re-checked ✓"` → P2 (verbatim, no number — inventing one is a §15 FAIL).
- **Sizes/type:** Mono-data style 12/18, ink-2 `#5F5C52`; the ✓ is Works `#1F7A3D`.
- **States:** non-interactive. Responsive: wraps as text, never truncates. Aria: plain text; ✓ decorative `aria-hidden`.
- **Must NOT do:** appear on unconfirmed ("Seen once") items; use the word "verified" or "evidence score".

### 10A.6 ProofTrail

- **Purpose:** show that screenshots exist, as a visual trail under ProofChip (structure borrowed per §12c; styling is ours).
- **Anatomy:** [thumbnail] 8px [thumbnail] 8px [thumbnail] 12px [overflow label, Mono-data ink-2] — exactly 3 thumbnails max.
- **Sizes/colours:** thumbnail 56×36px, radius 6px, border 1px `--line` `#E4E0D6`, bg paper `#FAF7F1`, inside: a flat mini-panel sketch in line colour + a step caption BELOW in Meta/label 11px ink-faint (e.g. "STEP 5", "STEP 6", "STEP 7"). Overflow label ONLY when a total exists: P1: total 7, shown 3 → "+4 more". P2: no total → NO overflow label, captions only.
- **States:** non-interactive in V1 (thumbnails are not links/buttons). No hover zoom, no lightbox in V1.
- **Responsive:** row never wraps below 3 thumbnails at ≥360px (56×3 + gaps = 184px, fits); caption may wrap.
- **Aria:** wrapper `role="img"`; P1 `aria-label="7 screenshots, 3 shown"`; P2 `aria-label="Screenshots from Maya's attempt (3 shown)"` (exact §9 patterns). Thumbnails themselves `aria-hidden`.
- **Must NOT do:** invent a count for P2; use real-looking fake screenshots with readable fake text; add gradients/shadows to thumbnails.

### 10A.7 TesterCard

- **Purpose:** one tester's live state on Watch live (equal weight for all 3 testers).
- **Anatomy (in order):** [header row: avatar 32px + name H3 + identity label Body-small ink-2] 12px [state line: symbol + word, weight 600] 8px [activity line, Body-small] 12px [browser-frame mock] 12px [StepList or collapsed line] [TakeoverPanel — Priya's card only, when blocked].
- **Colours:** card bg white, border line, radius 10px, padding 20px; avatar bg = tester colour, white initial; NO tester colour anywhere else in the card except avatar border/ring.
- **Filled examples (§4 live snapshot, verbatim):** Tom — state "✓ Finished", progress line "✓ All 6 attempts · Done" (see StepList). Maya — state "◐ Doing", activity "Buy a t-shirt — step 5 of 7 · At checkout — about to pay", progress "2 steps left". Priya — state "! Needs your help", activity "Track an order — waiting for a login", waiting "Waiting 6 minutes", NO step counts.
- **States:** card itself non-interactive. Hover: none. The frame inside is a labelled picture (`role="img"`, `aria-label` describing what the tester sees), never fake OS chrome.
- **Responsive:** cards 3-in-row ≥1024px, stack ≤900px (§2C.3); frame scales to card width, height proportional, never crops the activity line.
- **Must NOT do:** rank testers, show a failure before it happens (Maya step 6 is FORBIDDEN here), show step totals for Tom/Priya, colour the whole card by tester/status.

### 10A.8 StepList (with collapse toggle)

- **Purpose:** show an attempt's steps; finished work collapses (§12b).
- **Anatomy:** [completed block OR collapsed line + toggle] [current step, weight 600, with ◐ marker] [upcoming steps, ink-2].
- **Exact behaviour — Maya, Watch live:** steps 1–4 collapsed into ONE line: "✓ Steps 1–4 · Done" + toggle button "Show steps". Toggle: real `<button>`, min-height 44px, Button-label style, ink text, underline on hover, `aria-expanded="false"`, `aria-controls` = step list id. Click → expands to the 4 canonical step names (each: "✓ " + name, Grid-cell style), toggle text becomes "Hide steps", `aria-expanded="true"`. Click again → collapses, focus stays on toggle.
- **Exact behaviour — Tom, Watch live:** fully finished → ONE line only: "✓ All 6 attempts · Done". ATTEMPTS, not steps. No toggle (nothing to expand in live view).
- **Exact behaviour — Test results (finished):** full canonical list visible; failed step (Maya step 6 "Clicked Pay — nothing happened") carries ✕ in Broken `#C62F3B` + word styling; other steps carry ✓ in ink-2.
- **Sizes/spacing:** each step row padding 8px 0, 1px line divider between rows (except collapsed line); step number in Mono-data ink-faint, 24px wide column.
- **Colours:** current step text ink weight 600; completed ink-2; upcoming ink-faint. No background tints on rows.
- **Responsive:** never truncates a step name; names wrap to 2 lines if needed.
- **Aria:** list is `<ol>`; collapsed region `hidden` until expanded; toggle state per §11A matrix.
- **Must NOT do:** assert any step count for Tom or Priya; show Maya step 6/7 in Watch live; auto-expand on load.

### 10A.9 TakeoverPanel — BOTH states fully specced

- **Purpose:** the ONE place an owner unblocks a tester. Same component in Priya's TesterCard (Watch live) and in NeedsYouRow (Dashboard). Never build two versions.
- **Anatomy (state A — idle/waiting):** [title H3: "Priya needs your help"] 8px [body Body-small: "Log in to Priya's test browser to unblock Track an order."] 16px [primary button: "Take over Priya's browser"].
- **Anatomy (state B — owner in control):** [title H3: "You are in control"] 8px [body Body-small: "You are using Priya's test browser. Priya is paused."] 16px [button: "Hand back to Priya", `aria-pressed="true"`] — and the TesterCard frame above the panel is now the owner's frame (same frame component, owner label Meta/label: "YOUR VIEW").
- **Copy verbatim:** state A title/body/button exactly as above with the blocked tester's name + task substituted from data ("{Name} needs your help" / "Log in to {Name}'s test browser to unblock {Task}." / "Take over {Name}'s browser"). State B: "You are in control" / "You are using {Name}'s test browser. {Name} is paused." / "Hand back to {Name}".
- **Sizes/colours:** panel inside card, separated by 1px line top border, padding-top 16px, NO extra card/bg (never nest cards, R8). Button: workspace primary = ink `#111111` bg, white text, radius 0, padding 12px 20px, min-height 44px. Hover: ink at 85% opacity bg. Focus: white-surface ring does NOT apply — panel is on white, use ink ring (§2A.5 light rule).
- **Transitions:** click A button → state B, `aria-pressed` on B button = "true", focus MOVES to panel title (tabindex="-1") so screen-reader users hear "You are in control". Click B button → back to state A, focus returns to the A button.
- **Responsive:** button full-width at <640px. Panel never overlays/modal — it is inline, always.
- **Must NOT do:** open a modal; auto-hand-back on a timer; show for non-blocked testers; use red styling.

### 10A.10 NeedsYouRow

- **Purpose:** one blocked tester needing the owner, on Dashboard "Needs you". Admission rule (§7): a row exists ONLY if that tester is blocked and cannot continue without the owner.
- **Anatomy:** [avatar 24px inline] 12px [text block: line 1 Body weight 600: "Priya is stuck logging in — Track an order"; line 2 Body-small ink-2: "Waiting 6 minutes"] [right-aligned action button: "Help Priya"].
- **Sizes/colours:** row padding 16px 20px, bg card, border 1px line, radius 10px, gap 16px between rows if >1. Symbol: "!" in a circle in ink before line 1 (same needs-help symbol as TesterCard — never a different symbol per page).
- **Filled example:** exactly the Priya example above (§4 live snapshot: waiting 6 minutes, Track an order, login).
- **States:** row non-interactive; button = workspace secondary: white bg, 1px ink border, ink text; hover bg paper; focus ink ring. Clicking "Help Priya" goes to Watch live with Priya's TakeoverPanel in state A (it does NOT itself take over).
- **Responsive:** <640px button moves below text block, full-width.
- **Aria:** row is a list item in a `<ul aria-label="Needs your help">`; waiting time is text, updated at most once per minute, NOT a live region (no aria-live — avoid chatter).
- **Must NOT do:** appear in All-clear state; show non-blocked testers; show counts of non-urgent items.

### 10A.11 ProgressLine

- **Purpose:** progress in plain words + a thin bar (§12a), on Dashboard "Happening now" and Watch header.
- **Anatomy:** [line 1 Body: "{App} — testing now · Checked {x} of {y} attempts"] 8px [bar] — bar: height 8px, radius 4px, bg notchecked tint `#F0EEE7`, fill ink `#111111` width = x/y. NO status colours in this bar (progress is not a status).
- **Filled example:** "Thread & Co. — testing now · Checked 9 of 18 attempts", fill 50%. Watch variant lines (§8): "1 of 3 testers finished · 9 of 18 attempts done" then "9 attempts to go." as its own line in weight 600.
- **Per-tester patterns:** "{n} steps left" (Maya: "2 steps left"), "All steps completed" / "✓ All steps completed" (finished tester), NO line at all for a blocked tester beyond state + waiting.
- **States:** non-interactive. Row variant on Dashboard is a link to Watch live: whole row clickable, hover bg paper, focus ring on row.
- **Aria:** bar `role="img"` with `aria-label` = the full words line; visual bar `aria-hidden`. Never `role="progressbar"` with a bare % — words are the data.
- **Must NOT do:** show percentages, ETAs (the only time estimate in the product is "about 20 minutes", §4), or animated counting.

### 10A.12 MegaMenu

- **Purpose:** the ONLY marketing mega menu, under "PRODUCT ⌄".
- **Anatomy:** trigger button "PRODUCT" + chevron (rotates 180° when open) → panel: 3 columns = the 3 §3 groups in order; each column: [group label] then items stacked 16px apart.
- **Sizes:** panel max-width 880px, width = min(880px, viewport − 48px), bg card `#FFFFFF`, border 1px line, radius 12px, shadow `--shadow-panel`, padding 24px, column gap 32px, positioned under header, left-aligned to trigger, top offset 8px.
- **Typography:** group label = Meta/label ink-faint ("START HERE" / "SEE IT WORKING" / "GET YOUR ANSWERS"). Item name = Inter 15px/22px weight 600 ink + trailing "→" in ink-faint. Item description = Inter 13px/20px ink-2, max 2 lines. Item padding 8px; hover: bg paper `#FAF7F1` radius 6px on the item block; focus: ink ring on item link.
- **Content:** exactly the 8 items in §3, each destination ONCE, name + §3 description verbatim.
- **Behaviour/aria:** full spec in §11 + §11A: click-to-open (NEVER hover), `aria-haspopup="true"`, `aria-expanded`, Esc/outside-click/selection closes, focus returns to trigger.
- **Responsive:** ≤900px there is NO panel — groups become an accordion inside the mobile menu (same labels/order; accordion headers ≥44px, `aria-expanded` each).
- **Must NOT do:** open on hover; contain images, promos, or a featured card; contain "Start a test" as an item (removed, §3); link to non-existent destinations.

### 10A.13 ContextTabs

- **Purpose:** the in-test tab strip: exactly "Test results | Watch live", plus the context row above it.
- **Anatomy:** context row (44px): left Meta/label ink-2: "THREAD & CO. · TEST · SAT 31 OCT 2026"; below it the tablist: two tabs, gap 8px.
- **Sizes/colours:** each tab min-height 44px, padding 12px 16px, Button-label style. Unselected: ink-2 text, no underline, transparent bg. Selected: ink `#111111` text + 2px solid ink underline (box-shadow inset 0 -2px 0 ink, or border-bottom on inner span — underline must be exactly 2px). Hover (unselected): ink text. Focus: ink ring offset 2px (ring must not be clipped by the underline — add 2px padding-box room).
- **Behaviour/aria:** WAI-ARIA tablist (§11): `role="tablist"`, tabs `role="tab"` + `aria-selected`, panels `role="tabpanel"`, roving tabindex, ArrowLeft/Right/Home/End. Exactly ONE tab selected at any time; "Tests" is the active workspace nav item on BOTH tabs' views (§3).
- **Responsive:** tabs never shrink below 44px height; at <640px tabs take 50% width each, centred text.
- **Filled example:** on Test results view: "Test results" selected, "Watch live" unselected. On Watch live: reversed. No third tab ever.
- **Must NOT do:** add tabs ("Overview", "History"); use pill/background styling for selected state; navigate via hash in production.

### 10A.14 UrlIntakeForm

- **Purpose:** the ONLY intake: an app address → start a test. Appears twice on Landing (hero + final CTA), identical component.
- **Anatomy:** [label Meta/label: "YOUR APP'S ADDRESS"] 8px [row: input + primary button] 8px [message line: reserved min-height 22px so layout never jumps].
- **Sizes:** input height 48px, flex-grow, placeholder "yourapp.com" (placeholder is ink-faint AND never the only label — the visible label above is mandatory). Button: flame-deep bg `#BC4218`, white Button-label text "START A TEST", padding 12px 20px, min-height 48px in the form (form variant taller than default 44px), radius 0.
- **States (see §11A):** Pristine: line border, empty message line. Hover (button): bg flame-deep-hover `#A83A15`. Focus (input): ink ring 2px offset 2px + border ink. Error: input border Broken `#C62F3B` 1px + `aria-invalid="true"` + message in Broken `#C62F3B` at 13px/20px Inter (NOT mono), message text verbatim §6: empty → "Enter your app's address to start."; unparseable → "That doesn't look like a web address. Check it and try again." Message linked via `aria-describedby`. Success: message in ink-2: "We'll test https://…" echoing ONLY the parsed origin (e.g. "We'll test https://threadandco.example") — never echo path/query/credentials. Disabled (submitting): button ink at 40% + `aria-disabled`, text unchanged (no spinner).
- **Responsive:** ≥640px input+button on one row gap 12px; <640px stacked, button full-width below input.
- **Must NOT do:** navigate on invalid input; show a generic "Invalid URL" message; pre-fill a real customer URL; add extra fields (no email field, no password field, ever).

### 10A.15 Signature visual — Triptych panels + "Put together" strip (§5 components)

- **Panel anatomy:** [top edge: 3px solid tester colour] [header row: avatar 40px + name H3 + identity label Body-small ink-2] 16px [storefront mock: Thread & Co. header line, product line "Classic tee — $28", button sketch "Pay $28" as a flat ink-outline rectangle — a picture of a store, not a working button] 16px [outcome line: StatusPill-equivalent symbol+word, Grid-cell weight 600] 8px [their line, Body-small].
- **Panel sizes/colours:** bg card, border 1px line, radius 10px, padding 20px. Tom + Maya panels equal flexible width; Priya panel width 260px fixed on desktop (phone width), centred when stacked. Outcome lines verbatim (§5 table): Tom "✓ Worked — Bought it with no trouble." + note "Noticed: search suggestions flicker." Maya "✕ Broken — Pay button does nothing." + "I didn't know if I'd been charged." Priya "✓ Worked — Bought it on her phone." + "? Search kept timing out — couldn't check it."
- **Put-together strip anatomy:** full-width block under panels, margin-top 24px: [Meta/label "PUT TOGETHER"] 12px [3 flat rows Body: "Works — Browsing, sign-up, discount codes" / "Broken — Pay button (found by Maya, checked again)" / "Couldn't check — Search, on Priya's phone"] 16px [verdict pill: ink bg `#111111`, white text, radius 999px, padding 8px 20px, Button-label style: "Verdict · Not ready yet"].
- **Hard rules:** NO arrows, NO connecting lines, NO funnel between panels (any connector graphic = §15 FAIL). Flat colours only.
- **Motion:** panels fade in together ONCE on load (opacity 0→1, 400ms, no translate/slide); `@media (prefers-reduced-motion: reduce)` snippet in §11A disables it completely.
- **Aria:** figure `role="img"`, `aria-label="The same store, seen by three testers. Tom bought it with no trouble. Maya's Pay button did nothing. Priya bought it on her phone, but search kept timing out. Put together, the verdict is: Not ready yet."` Inner content `aria-hidden` for the figure variant; the compact Results strip variant keeps text readable (it is content, not only a figure) — implement Results variant as real text with the same layout.
- **Compact variant (Test results):** same panels at 60% scale (avatar 24px, padding 16px, storefront mock omitted — header + outcome + their line only), strip rows identical, directly under VerdictBlock, margin 24px 0.
- **Must NOT do:** link panels to anything; animate on scroll; reorder testers (order is always Tom, Maya, Priya).

## §6A Landing page — element-by-element walkthrough (top → bottom)

Format per element: name — component — exact copy — tokens/type — spacing — behaviour. Copy in quotes is verbatim; do not edit punctuation.

1. **Announcement bar** — plain bar — copy: "New — see a full example test, start to finish →" (the "→" is part of the link) — bg plum `#221244`, white Meta/label centred, height 36px — spacing: none above, header directly below — behaviour: whole text is ONE link to Example report; hover underline; focus white ring (§2A.5 dark rule).
2. **Header** — §3 marketing header — height 64px, paper bg, 1px line bottom border — left: wordmark "MarketTwin" Inter 18px weight 650 ink (NOT serif) — centre/left nav: "PRODUCT ⌄" (MegaMenu trigger, §10A.12), "HOW IT WORKS", "EXAMPLE REPORT" all Button-label style ink — right: "SIGN IN" text button (Button-label, ink, no border; in production routes to real sign-in; never fake) + primary button "START A TEST" (flame-deep bg) — spacing inside: 24px page padding, 32px gaps between nav items, 16px between SIGN IN and primary — behaviour: header is NOT sticky in V1.
3. **Hero section** — padding 88px top, 64px bottom, paper bg — elements in order:
   - Eyebrow — Meta/label, flame-deep `#BC4218` text: "YOUR APP, TESTED LIKE A PERSON" — 16px below.
   - H1 — Display style (56/64, 40/46 mobile): "Know if your app is ready — before your customers find out." — max-width 720px — 24px below.
   - Lede — Body 16/26 ink-2, max-width 640px: "Give us your app's address. Three testers — an expert, a first-timer, and someone in a hurry on their phone — try to use it the way real people do. You get one honest answer, with proof: what worked, what broke, and what we could not check." — 16px below.
   - Promise line — Body weight 600 ink: "We only call something broken when the evidence proves it — twice." — 32px below.
   - URL form — UrlIntakeForm (§10A.14), max-width 560px — message line reserved 22px.
   - Segmented hero control — WAI-ARIA tablist (§11), margin-top 32px: three tabs (Button-label, min-height 44px, selected = ink + 2px ink underline exactly like ContextTabs): "I have an app to test" / "Show me an example" / "How it works". Panels: tab 1 shows the URL form focus state + one Body-small line "One address is enough. No setup, no scripts."; tab 2 shows the Example card (§6 step 6) scrolled into the supporting panel area; tab 3 shows the 3 How-it-works steps as a compact list. Switching changes ONLY the supporting panel, never navigates.
4. **Signature visual section** — §10A.15 triptych + put-together strip — bg paper — padding 64px top/bottom — heading: NONE (the figure speaks; do not add a headline above it) — spacing after strip: 0 (stat band follows).
5. **Stat band** — boxless (NO card, NO bg, NO border except 1px line top + bottom) — padding 40px 0 — 4 figures in a row (2×2 grid <640px), each: Stat-numeral (Newsreader 40/44 ink) on top, caption Body-small ink-2 below, centred pair — figures + captions verbatim: "18" / "attempts in a full test" · "3" / "testers, 3 viewpoints" · "2" / "problems confirmed in the example" · "0" / "scores you have to decode" — gap 32px between pairs.
6. **Example card section** — heading H2-marketing: "A real test, written the way yours will be." — 24px below: Example card (card styling §2C.2, padding 24px): ContextTabs variant with tabs "Test results | Watch live" controlling two panes INSIDE the card: Results pane = VerdictBlock compact (word "Not ready yet" at 32/40 + reason + honest-inputs strip) + CoverageBar + P1/P2 rows (title + ProofChip only, no trails in the card) + 3 feelings quotes (Quote style, attribution Meta/label). Watch pane = 3 tester rows at §4 live snapshot (Tom finished line, Maya step 5 activity, Priya needs-help line) — Maya step 6 must NOT appear. Tab behaviour = §11 tablist rules.
7. **How it works** — bg band-peach `#FCE8D8` flat, padding 88px 0 — heading H2-marketing ink: "How it works" — 40px below: 3 steps in a row (stack ≤900px), each: step number = Stat-numeral flame-deep `#BC4218` ("1"/"2"/"3", serif numeral is allowed here as a graphic numeral — it is NOT data), then H3 ink title, then Body ink text — verbatim: "1 · Tell us the address — One address is enough. No setup, no scripts." / "2 · Testers try it for real — They click, type and pay like people do — and get stuck like people do." / "3 · You get one answer — Worked, broken, or could not check — each with the screenshots to prove it." (Title before the em-dash, body after it.)
8. **What you get** — bg band-lilac `#E4E0F5` flat, padding 88px 0 — heading H2-marketing ink: "What you get" — content: the verdict anatomy displayed as real components on white cards (VerdictBlock, CoverageBar, one problem row with ProofChip, one Quote) each with ONE annotation sentence in Body ink below it: VerdictBlock → "One word, one reason, and what the test was based on." CoverageBar → "Every attempt counted, including the ones we could not check." Problem row → "A problem counts only when it fails again on a second check." Quote → "How it felt, in the tester's own words — never a score."
9. **Feelings section** — paper bg, padding 88px 0 — heading H2-marketing: "How it felt" — 3 pull-quotes stacked or in 3 columns (stack ≤900px), each: Quote style (Newsreader italic 22/32 ink), attribution below in Meta/label ink-2: name + identity + task, e.g. "MAYA · FIRST-TIME USER · BUY A T-SHIRT". Quotes verbatim from §4 feelings. Gap 40px between quotes.
10. **Final CTA** — bg band-rose `#F9DEE4` flat, padding 96px 0 — H2-marketing (serif, ink, 32/40 — NOT Display size): "Find out before your customers do." — 24px below: UrlIntakeForm (second instance, §10A.14) — 16px below: Body-small ink: "A full test takes about 20 minutes." (the ONLY time estimate, §4).
11. **Footer** — bg footer-deep `#17102E` — padding 64px top, 0 bottom (bottom bar handles bottom) — columns (stack <640px): column headers Meta/label white; links Body-small white 70%: use §3 names only ("Dashboard", "Watch live", "Test results", "Testers", "Example report", "How it works", "Your apps", "Add an app", "Settings") — non-existent destinations = inert white-70% text, NOT links, no hover — NO "How this page is designed"/Design-Notes block (§13) — bottom bar: 1px top border white 15%, padding 16px 24px, flex row space-between: LEFT Meta/label white 70%: "© 2026 MarketTwin · Concept design" — RIGHT Meta/label white 70%: "Developed by SJ" — that is the complete bottom bar, nothing else in it.

## §7A Dashboard — element-by-element walkthrough

Chrome: workspace header 56px (card bg, wordmark left, workspace nav §3 centre/left, owner avatar 32px right — initials "AM" on ink bg in demo). Exactly ONE header, ONE "Sample data" chip when demo data is shown (Meta/label, notchecked tint bg, placed next to the H1, 12px gap). Container: fluid, 32px gutters (16px mobile), sections separated by 32px, page top padding 32px.

Section header pattern (used by ALL dashboard sections): eyebrow Meta/label ink-faint ABOVE the header — eyebrow texts: "NEEDS YOU" / "HAPPENING NOW" / "YOUR APPS" / "RECENT TESTS" — then H2-workspace ink header verbatim: "Needs you" / "Happening now" / "Your apps" / "Recent tests" — 8px eyebrow-to-header, 16px header-to-content. No icons on headers. No "View all" links unless the destination exists in §3.

**State: Live moment (default demo state):**

1. Page H1 — H1-workspace: "Dashboard" — 8px below: Body-small ink-2 line: "Thread & Co. is being tested now. One tester needs your help."
2. **Needs you** — 1 NeedsYouRow (§10A.10) with Priya example verbatim. No other rows.
3. **Happening now** — 1 linked ProgressLine row (§10A.11): "Thread & Co. — testing now · Checked 9 of 18 attempts" + bar 9/18 + right Meta/label "Started 21 minutes ago".
4. **Your apps** — 1 app card (padding 20px): header row: app name H3 "Thread & Co." + Meta/label ink-faint "THREADANDCO.EXAMPLE"; 12px: verdict line Body weight 600: "Not ready yet · Sat 31 Oct 2026"; 12px: change chips row (3 separate small outline chips, Body-small, 1px line border, radius 999px, padding 4px 12px, gap 8px): "2 fixed" / "1 still broken" / "1 new" — NEVER netted, never "+1"; 12px: VerdictStrip (§10A.4, 2 segments); 16px: action link-button "See test results" (secondary button style).
5. **Recent tests** — divider rows (1px line between, padding 16px 0, Grid-cell style): row 1: "Thread & Co. · Sat 31 Oct 2026 · Testing now · 9 of 18 attempts"; row 2: "Thread & Co. · Wed 21 Oct 2026 · Stopped early · 6 of 18 attempts" — NO verdict word on row 2 anywhere.

**State: All clear:** sections 1–2 are REMOVED and replaced, in the same position (directly under the H1 line), by ONE calm line: Body 16px ink, no card, no bg, no icon: "Nothing needs you right now." — 32px below it, "Your apps" follows (app card shows finished verdict + delta chips as above, ProgressLine/Happening-now absent). H1 line becomes: "No test is running right now."

**State: Brand new:** the page is ONLY: H1 (H1-workspace is the page H1; the serif headline below is display text inside the empty state — heading hierarchy: page H1 = "Dashboard" in header area, empty-state headline is an H2 in Newsreader 32/40): "Your dashboard will live here." — 16px: Body ink-2: "Add an app and we will test it like a person would — then show you what worked, what broke, and what we could not check." — 24px: primary workspace button (ink bg): "Add an app". Nothing else: no section headers, no empty boxes, no zero cards, no sample data chip.

## §8A Watch live — element-by-element walkthrough

Chrome: workspace header + ContextTabs block (§10A.13): context row "THREAD & CO. · TEST · SAT 31 OCT 2026", tabs with "Watch live" selected. "Tests" active in workspace nav. ONE "Sample data" chip next to H1 if demo data.

1. H1 — H1-workspace style, text exactly: "Watch live" (the §3 destination name is the view title). Do not invent an alternative title.
2. Snapshot lines — directly under H1, 12px gap: line 1 Body: "1 of 3 testers finished · 9 of 18 attempts done" — line 2 Body weight 600 ink (8px below line 1): "9 attempts to go." — line 3 Body-small ink-2 (8px below): "Started 21 minutes ago". These three lines are the header block; no progress % anywhere.
3. Tester cards row — 32px below header block; gap 32px (24px at 900–1199px); order Tom, Maya, Priya — each TesterCard (§10A.7) line-by-line for the §4 snapshot:

**Tom card:** header: avatar 32px violet `#6842D6`, initial "T", name "Tom" (H3), label "Expert" (Body-small ink-2). State line: "✓ Finished" (ink, weight 600; ✓ in Works green). Activity line: "All tasks attempted." Progress/collapse line (§10A.8): "✓ All 6 attempts · Done". Frame: finished storefront picture, `aria-label="Tom's test browser: Thread & Co. order complete page"`. No takeover. No step list. No step counts beyond the attempts line.

**Maya card:** avatar teal `#0F766E` "M", name "Maya", label "First-time user". State: "◐ Doing". Activity: "Buy a t-shirt — step 5 of 7 · At checkout — about to pay". Progress: "2 steps left". Frame: checkout picture, `aria-label="Maya's test browser: Thread & Co. checkout, about to pay"`. StepList collapsed: "✓ Steps 1–4 · Done" + "Show steps" toggle (§10A.8); current step shown below toggle: "5 · Went to checkout" marked current — NOTE: canonical step 5 text is "Went to checkout"; the activity line's "At checkout — about to pay" is the activity description, do not merge them. Steps 6–7 are NOT rendered in this view (not even greyed — absent).

**Priya card:** avatar copper `#96521F` "P", name "Priya", label "Impatient mobile user". State: "! Needs your help" (ink; ! in ink circle). Activity: "Track an order — waiting for a login". Waiting line Body-small ink-2: "Waiting 6 minutes". NO progress line, NO step counts. Frame: order-tracking login picture with visible texts "Track your order" and "Log in to see where your order is." — `aria-label="Priya's test browser: Thread & Co. order tracking login"` — NEVER a checkout login in this frame. TakeoverPanel state A below frame (§10A.9 verbatim Priya copy).

4. Footer of view: nothing. No summary bar, no totals recap (totals live on Test results).

## §9A Test results — element-by-element walkthrough

Chrome: workspace header + ContextTabs with "Test results" selected; "Tests" active in nav; one "Sample data" chip if demo.

Order + spacing (32px between sections unless stated):

1. **VerdictBlock** (§10A.2 full variant) — the verdict word "Not ready yet" is the view H1.
2. **Three-looks strip** — §10A.15 compact variant — margin 24px 0 (override of 32px, intentional).
3. **Coverage section** — header H2-workspace: "What we checked" — 16px: CoverageBar (§10A.3) with headline + legend verbatim.
4. **Tasks × testers grid** — header H2-workspace: "Task by task" — table: header row: blank corner + 3 tester columns (avatar 24px + name + label); row header = task name (Grid-cell weight 600) numbered "1."–"6." Mono-data; each cell: symbol + word centred-left, status text colour (§2A.3) on white (tints only in pills — grid cells use WHITE bg + coloured symbol/word; row separators 1px line; cell padding 12px). Reason lines: under task 3 row, Body-small ink-2 spanning: "Not checked for Tom and Priya — The plan gave this task to Maya only." Under task 4, in Priya's cell area: "? Could not check — Search kept timing out on Priya's phone connection." Under task 6 row: "Not checked for Tom and Maya — Needs a real order email, which the plan did not include."
5. **Comparison strip** — header Meta/label: "SINCE THE LAST TEST (WED 21 OCT 2026)" — 12px: 3 chips exactly like Dashboard change chips: "Fixed 2" / "Still broken 1" / "New 1" + Body-small note: "The previous test stopped early after 6 of 18 attempts, so it has no verdict."
6. **Problems** — header H2-workspace: "Problems we confirmed" — P1 card then P2 card (gap 24px), each: title H3, Meta/label line "BUY A T-SHIRT · FOUND BY MAYA, FIRST-TIME USER" (P2: "SEE AN ERROR WHEN THE EMAIL IS ALREADY USED · FOUND BY MAYA, FIRST-TIME USER"), description Body (§4 wording verbatim), ProofChip, ProofTrail (P1 only trail with "+4 more"; P2 trail without overflow), StepList full (P1: Maya's 7 steps, step 6 ✕ Broken style; P2: no step list — P2 has no canonical steps, do not invent). Below both cards: seen-once line Body-small ink-2: "Seen once, not counted as a problem: search suggestions flicker (Tom)."
7. **How it felt** — header H2-workspace: "How it felt" — 3 quotes, Quote style, layout as Landing feelings (stacked rows with 1px line separators here, not columns), attributions Meta/label: "MAYA · FIRST-TIME USER · BUY A T-SHIRT" / "TOM · EXPERT · SEE AN ERROR WHEN THE EMAIL IS ALREADY USED" / "PRIYA · IMPATIENT MOBILE USER · SEARCH FOR A T-SHIRT AND USE FILTERS". Quotes verbatim §4.
8. **What we did not check** — header H2-workspace: "What we did not check" — plain list (Body, 12px row gap, no card): line 1 "1 attempt could not be checked — Priya's search timed out on her connection." line 2 "Task 3 for Tom and Priya — the plan gave this task to Maya only." line 3 "Track an order for Tom and Maya — needs a real order email, which the plan did not include." (These lines are verbatim from §9; do not substitute other reasons — "payment test mode" or any other invented reason is a §15 FAIL.)

## §4A Copy deck — EVERY user-visible string, grouped by page

Lift strings verbatim from this table. A reviewer diffs the build against this table: any visible string in the build that is NOT in §4A/§4/§6A–§9A is a FAIL; any §4A string rendered with different wording/punctuation is a FAIL. `{n}`/`{x}`/`{Name}`/`{Task}` are data substitutions — everything around them is fixed.

### Global / chrome

| String | Where |
|---|---|
| "MarketTwin" | Wordmark |
| "PRODUCT" / "HOW IT WORKS" / "EXAMPLE REPORT" / "SIGN IN" / "START A TEST" | Marketing header |
| "New — see a full example test, start to finish →" | Announcement bar |
| "Dashboard" / "Needs your help" / "Your apps" / "Tests" / "Testers" / "Settings" | Workspace nav |
| "Test results" / "Watch live" | In-test tabs |
| "THREAD & CO. · TEST · SAT 31 OCT 2026" | Context row (data-driven pattern: "{APP} · TEST · {DATE}") |
| "Sample data" | Demo chip |
| "© 2026 MarketTwin · Concept design" | Footer bottom bar, left |
| "Developed by SJ" | Footer bottom bar, right |
| "Start a test" / "Add an app" / "See test results" / "Take over" / "Hand back" | Core actions (pattern family, §1 R5) |

### Patterns with data (use exactly these templates)

| Pattern | Filled example |
|---|---|
| "Waiting {n} minutes" | "Waiting 6 minutes" |
| "{n} steps left" | "2 steps left" |
| "Checked {x} of {y} attempts" | "Checked 9 of 18 attempts" |
| "{x} of {y} testers finished" | "1 of 3 testers finished" |
| "{n} attempts to go." | "9 attempts to go." |
| "Started {n} minutes ago" | "Started 21 minutes ago" |
| "✓ Steps {a}–{b} · Done" | "✓ Steps 1–4 · Done" |
| "✓ All {n} attempts · Done" | "✓ All 6 attempts · Done" |
| "{n} screenshots · re-checked ✓" | "7 screenshots · re-checked ✓" |
| "Proof attached · re-checked ✓" | (P2, no substitution) |
| "+{n} more" | "+4 more" |
| "{Name} needs your help" | "Priya needs your help" |
| "Take over {Name}'s browser" / "Hand back to {Name}" | "Take over Priya's browser" / "Hand back to Priya" |
| "Help {Name}" | "Help Priya" |
| "We'll test {origin}" | "We'll test https://threadandco.example" |
### Landing page strings (in addition to §6/§6A, which are authoritative for full sentences)

"YOUR APP, TESTED LIKE A PERSON" · "Know if your app is ready — before your customers find out." · "We only call something broken when the evidence proves it — twice." · "yourapp.com" (placeholder) · "YOUR APP'S ADDRESS" (form label) · "I have an app to test" · "Show me an example" · "How it works" · "One address is enough. No setup, no scripts." · "18" + "attempts in a full test" · "3" + "testers, 3 viewpoints" · "2" + "problems confirmed in the example" · "0" + "scores you have to decode" · "A real test, written the way yours will be." · "What you get" · "How it felt" · "Find out before your customers do." · "A full test takes about 20 minutes." · Form errors: "Enter your app's address to start." / "That doesn't look like a web address. Check it and try again."

### Dashboard strings

"Dashboard" (H1) · "NEEDS YOU" / "Needs you" · "HAPPENING NOW" / "Happening now" · "YOUR APPS" / "Your apps" · "RECENT TESTS" / "Recent tests" · "Nothing needs you right now." · "Your dashboard will live here." · "Priya is stuck logging in — Track an order" · "Thread & Co. — testing now · Checked 9 of 18 attempts" · "2 fixed" / "1 still broken" / "1 new" · "Not ready yet · Sat 31 Oct 2026" · "Stopped early · 6 of 18 attempts" · Section eyebrow style is Meta/label for all four headers — no other dashboard headers exist.

### Watch live strings

"1 of 3 testers finished · 9 of 18 attempts done" · "9 attempts to go." · "Started 21 minutes ago" · "✓ Finished" · "◐ Doing" · "! Needs your help" · "✓ All steps completed" (= Tom's finished phrasing family; the rendered Tom line is "✓ All 6 attempts · Done" per §10A.8 — use the attempts line on the card, "All steps completed" is the approved generic pattern only) · "2 steps left" · "Show steps" / "Hide steps" · "At checkout — about to pay" · "Track an order" / "Log in to see where your order is." (frame texts) · "You are in control" · "You are using Priya's test browser. Priya is paused." · "YOUR VIEW" (frame label in takeover state B).

### Test results strings

"Not ready yet" · "11 of the 14 attempts we could check worked." · "What we checked" · "Task by task" · "Problems we confirmed" · "How it felt" · "What we did not check" · "SINCE THE LAST TEST (WED 21 OCT 2026)" · "Fixed 2" / "Still broken 1" / "New 1" · "Seen once, not counted as a problem: search suggestions flicker (Tom)." · "Pay button does nothing" · "Sign-up error is hidden" · All §9 did-not-check lines verbatim (§9A item 8).

### Aria-labels specified in this document (implement verbatim, data-substituted)

CoverageBar: "11 of the 14 attempts we could check worked. 2 broken, 1 could not be checked, 4 not checked." · Triptych figure: full sentence in §10A.15 · ProofTrail P1: "7 screenshots, 3 shown" · ProofTrail P2: "Screenshots from Maya's attempt (3 shown)" · Tester frames: the three labels in §8A · VerdictStrip: "{App} test history: Wed 21 Oct 2026, stopped early, no verdict. Sat 31 Oct 2026, Not ready yet." · ProgressLine bar: same text as its visible words line.

### Empty / error / state strings (complete list — no others may be invented)

Brand-new dashboard: §7A brand-new copy only. All-clear: "Nothing needs you right now." only. Form errors: the two §6 messages only. No 404/empty-search/generic error copy is specced — if a real state needs one, flag to owner (§16), do not invent.

## §11A State matrices, keyboard map, and motion

### §11A.1 State matrices — visible + aria result per transition

**MegaMenu**

| State | Visible | Aria / DOM | Entered by |
|---|---|---|---|
| Closed | Trigger only, chevron down | `aria-expanded="false"`, panel absent (not just hidden) | Page load; Esc; outside click; selection |
| Open | Panel per §10A.12, chevron up | `aria-expanded="true"`, panel `role="menu"` groups labelled | Click / Enter / Space on trigger (NEVER hover) |
| Open + item focused | Item bg paper, ink ring | Focus is ON the item link | Tab into panel / arrow navigation |

**TakeoverPanel**

| State | Visible | Aria / DOM | Entered by |
|---|---|---|---|
| A — idle | Title "{Name} needs your help", body, "Take over {Name}'s browser" button | Button `aria-pressed="false"` (or no pressed attr — pick `aria-pressed` on the toggle pair and be consistent) | Page load when tester blocked; hand-back click |
| B — owner control | Title "You are in control", body "{Name} is paused", "Hand back to {Name}" button, frame labelled "YOUR VIEW" | Button `aria-pressed="true"`; focus moved to title (`tabindex="-1"`) on entry | Click A button |
| Return to A | State A restored exactly | Focus returns to the A button | Click B button |

**StepList**

| State | Visible | Aria | Entered by |
|---|---|---|---|
| Collapsed | "✓ Steps 1–4 · Done" + "Show steps" | Toggle `aria-expanded="false"`, region `hidden` | Load (default) |
| Expanded | 4 canonical steps listed + "Hide steps" | `aria-expanded="true"`, region visible, toggle keeps focus | Click toggle |
| Finished-single-line (Tom) | "✓ All 6 attempts · Done", no toggle | Plain text, no toggle in DOM | Load when tester finished |

**UrlIntakeForm**

| State | Visible | Aria | Entered by |
|---|---|---|---|
| Pristine | Line border, empty reserved message line (22px) | `aria-invalid` absent | Load |
| Error-empty | Broken border, "Enter your app's address to start." 13px Broken | `aria-invalid="true"`, msg id in `aria-describedby` | Submit with empty input |
| Error-unparseable | Broken border, "That doesn't look like a web address. Check it and try again." | Same as above | Submit with unparseable input |
| Success | Ink-2 message "We'll test {origin}", border returns to line/ink focus | `aria-invalid="false"`, msg in `aria-describedby` | Submit with valid address |

**Tabs (ContextTabs, hero segmented control, example-card tabs)**

| State | Visible | Aria | Entered by |
|---|---|---|---|
| Selected | Ink text + 2px ink underline, min-height 44px | `role="tab"`, `aria-selected="true"`, `tabindex="0"`, panel visible | Load (first / current view); click; arrow-key move + activation |
| Unselected | Ink-2 text, no underline | `aria-selected="false"`, `tabindex="-1"`, panel `hidden` | Load; another tab selected |

### §11A.2 Keyboard interaction table — every row must work

| Component | Key | Focus location before | Behaviour |
|---|---|---|---|
| MegaMenu trigger | Enter / Space / Click | Trigger | Opens panel, `aria-expanded="true"`, focus stays on trigger; first Tab moves into panel |
| MegaMenu open | Escape | Anywhere inside panel/trigger | Closes panel; focus RETURNS to the trigger that opened it (desktop trigger AND mobile Menu button — test both) |
| MegaMenu open | Tab | Last item | Focus leaves panel to next page element; panel closes on focus-out / outside interaction |
| MegaMenu open | Click outside | — | Closes; no focus change forced |
| Mobile accordion | Enter / Space | Group header | Toggles group, `aria-expanded` flips; other groups unchanged |
| Any tablist | ArrowRight / ArrowLeft | A tab | Moves focus + selection to next/previous tab (wrap at ends); panel updates |
| Any tablist | Home / End | A tab | First / last tab selected + focused |
| StepList toggle | Enter / Space | Toggle | Expands/collapses; focus STAYS on toggle; label flips Show/Hide |
| Takeover buttons | Enter / Space | Button | State A↔B per §11A.1; on entering B focus moves to panel title; on returning focus returns to A button |
| UrlIntakeForm | Enter in input | Input | Submits (same as button click); validation per §10A.14; NEVER navigates on error |
| All buttons/links | Tab / Shift+Tab | Previous element | Visible focus ring (§2A.5) on every stop; no focus traps anywhere; no positive `tabindex` values anywhere in the build |

### §11A.3 Focus, motion, and reduced-motion — exact CSS

```css
:focus-visible{outline:2px solid #111111;outline-offset:2px;}
.on-dark:focus-visible{outline:2px solid #FFFFFF;outline-offset:2px;}
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{animation:none!important;transition:none!important;}
  .triptych-panel{opacity:1!important;}
}
```

Rules: `.on-dark` applies to elements on plum, footer-deep, ink buttons, and flame-deep buttons. Triptych fade is the ONLY entrance animation in the product: `opacity 400ms ease, no transform`. No other transitions longer than 150ms (hover colour changes only). No scroll-jacking, no parallax, no auto-playing anything, no count-ups.

## §15A Expanded acceptance — numbered pass/fail test cases + measurement checks

Run EVERY case. Record PASS/FAIL per case number. One FAIL = not done (Definition of Done, §0). "Measure in the built UI" means: browser devtools / rendered DOM measurement of the BUILT page, not reading the CSS file.

### Data (D)

- D1. Feed the §4B JSON → open Test results → expect: totals line "11 of the 14 attempts we could check worked." exactly once, verdict "Not ready yet", strip "14 of 18 attempts checked · 3 testers · 2 problems confirmed · Sat 31 Oct 2026".
- D2. Same payload → Dashboard all-clear → expect identical verdict word + date; change chips read "2 fixed", "1 still broken", "1 new" as THREE chips.
- D3. Same payload → Landing example Results pane → expect identical verdict/reason as D1. Any differing number between D1/D2/D3 = FAIL (R1 broken).
- D4. Search rendered output for Tom + any step count ("7 steps", "steps" near Tom) → expect ZERO. Search for Priya + step counts → ZERO.
- D5. P2 problem block → expect chip "Proof attached · re-checked ✓" and NO digit before "screenshots" in that block.
- D6. Previous test (Wed 21 Oct 2026) anywhere → expect "Stopped early · 6 of 18 attempts" and NO verdict word adjacent.
- D7. Feelings sections (Landing + Results) → expect the 3 §4 quotes character-identical, attributions matching §9A item 7.
- D8. Watch live → expect Maya at step 5, text "Clicked Pay" ABSENT from the entire view; Priya waiting "6 minutes"; Tom line "✓ All 6 attempts · Done".

### Colours (C)

- C1. Computed style of page bg = `#FAF7F1`; card bg = `#FFFFFF`; footer bg = `#17102E`; announcement bg = `#221244`.
- C2. Every status pill: measure text + bg → matches §2A.3 pair for its status; symbol present in DOM text.
- C3. Could-not-check colour in pill, legend swatch, AND bar segment → all three compute to `#8A5F00` / tint pair as specced.
- C4. Tester colours appear ONLY in avatar/ring/top-edge elements: screenshot each view at 1440px and inspect — any Tom/Maya/Priya hex on text/button/bar = FAIL.
- C5. Flame `#E4572E`: grep rendered CSS + inspect graphics — appears in NO text element's color and NO button background. Buttons compute to `#BC4218`, hover `#A83A15`.

### Strings (S) — corrected grep commands (run in repo root, UI source only)

```bash
grep -RInE "Run a test|Click here|Learn more|deterministic|ledger|mission|persona|inconclusive|blocks checkout completely" src/ --include='*.tsx' --include='*.ts' --include='*.jsx' | grep -v "spec\|test fixtures" # expect: no UI-string hits; "Submit"/"OK" checked manually as button labels only (form internals/APIs exempt)
grep -RInE "linear-gradient|radial-gradient|backdrop-filter" src/ --include='*.css' --include='*.tsx' # expect ZERO (backdrop-filter:none is the only allowed match)
grep -RIn "#777777\|#777\b" src/ # expect ZERO
grep -RIn "#E4572E" src/ # expect hits ONLY in token definition + graphic components, NEVER in a text/button style
```
- S1. Every button label in the build is in §4A or is a §1 R5 pattern. Manual pass, list them.
- S2. No string in the rendered build is absent from §4A/§4/§6A–§9A. Manual diff per page.
### Naming (N)

- N1. Mega menu opened → count items = 8, groups = 3, each §3 destination appears exactly once, descriptions match §3.
- N2. Dashboard with 0 blocked testers → "Needs your help" has NO badge in DOM. Block 1 tester → badge appears with count 1.
- N3. Each view → exactly ONE workspace nav item has active styling; it is "Tests" on both Test results and Watch live, "Dashboard" on Dashboard.
- N4. Headers: landing shows marketing header + announcement; workspace views show exactly ONE header and NO announcement bar.

### Interactions (I)

- I1. MegaMenu: click opens; Esc closes + focus on trigger; outside click closes; mobile (≤900px) accordion opens/closes with `aria-expanded` flipping; Esc in mobile menu returns focus to the Menu button.
- I2. Every tablist: ArrowRight/Left/Home/End per §11A.2; exactly one panel visible at all times.
- I3. StepList toggle: click → expands with 4 canonical step names, label "Hide steps"; click again → collapsed; focus never leaves toggle.
- I4. Takeover: click A → state B, title "You are in control", focus on title; click Hand back → state A restored; Dashboard "Help Priya" lands on Watch with panel in state A.
- I5. URL form (both instances): empty submit → error-empty message, no navigation, URL unchanged; "not a url !!" → error-unparseable message; "threadandco.example/path?x=1" → success message "We'll test https://threadandco.example" (origin only).
- I6. No element anywhere traps focus; full keyboard walk of each view reaches every interactive element in visual order.

### Accessibility (A)

- A1. Measure EVERY interactive element's rendered height/width → all ≥44px in at least one dimension for touch (tabs exactly: min-height ≥44px measured).
- A2. Spot-measure contrast pairs from §2A.5 in rendered UI (devtools contrast tool) → all ✅ rows pass; confirm NO white-on-`#E4572E` exists anywhere.
- A3. Each view/state has exactly ONE `<h1>`; heading levels never skip.
- A4. Enable reduced-motion in OS/browser → reload landing → triptych fully visible immediately, no fade.
- A5. Focus ring visible on every Tab stop (light ring on light surfaces, white ring on plum/footer/buttons).

### Responsive (R)

- R1. At 360, 390, 768, 1024, 1440px widths: `document.documentElement.scrollWidth <= innerWidth` on all 4 views (no horizontal overflow).
- R2. At ≤900px: triptych stacked, Priya panel 260px centred; tester cards stacked; mega panel absent, accordion present.
- R3. At <640px: stat band 2×2; URL form stacked full-width button; footer bottom bar stacked with "Developed by SJ" under the © line.

### Measurement checks (M) — measure in the built UI

| # | Element | Expected |
|---|---|---|
| M1 | Announcement bar height | 36px |
| M2 | Marketing / workspace header height | 64px / 56px |
| M3 | Context row height | 44px |
| M4 | ContextTabs tab height | ≥44px |
| M5 | Coverage bar height / radius | 14px / 7px |
| M6 | Verdict strip segment height | 8px |
| M7 | Avatar diameters | 40px triptych, 32px cards, 24px inline |
| M8 | Proof thumbnail size | 56×36px |
| M9 | Card padding / verdict block padding | 20px / 24px |
| M10 | Card radius / button radius / pill radius | 10px / 0 / 999px |
| M11 | Marketing section vertical padding | 88px (64–96 allowed only where §6A states) |
| M12 | Workspace section gap | 32px |
| M13 | Mega panel width at 1440px viewport | 880px, radius 12px |
| M14 | Input height / button min-height | 48px / 44px (48px in URL form) |
| M15 | Hairlines | 1px, colour `#E4E0D6` |

## §17 Common mistakes — wrong → right (every row was a real drift failure)

| # | WRONG (never ship) | RIGHT (ship this) | Why |
|---|---|---|---|
| 1 | Tom: "All 7 steps · Done" | Tom: "✓ All 6 attempts · Done" | 7 is MAYA's step count for ONE attempt; Tom finished 6 ATTEMPTS |
| 2 | Priya: "5 steps left after you help" | No progress line for Priya; state + "Waiting 6 minutes" only | Priya's step totals were never defined — inventing them breaks R1/R2 |
| 3 | White text on `#E4572E` button | White text on `#BC4218` (flame-deep) | `#E4572E` pairing is 3.68:1, FAILS AA |
| 4 | "79% success" / score / gauge | "11 of the 14 attempts we could check worked." | Denominators always; no naked scores (R2) |
| 5 | Different totals hand-written per page | One payload; every view derives from §4B shape | Per-page numbers drift and contradict (R1) |
| 6 | Maya's pay failure shown in Watch live | Watch shows step 5 only; failure exists only in finished results | Live view never shows a failure before it happens |
| 7 | Priya frame shows a checkout login | Priya frame shows Track-an-order login | Her checkout PASSED; she is blocked on Track an order |
| 8 | Problem 1: "blocks checkout completely" | "When Maya tapped Pay, nothing happened. Tom and Priya paid without trouble." | Two of three paid fine — "completely" is false |
| 9 | Did-not-check reason: "payment test mode was unavailable" | "Priya's search timed out on her connection." (+ §9 lines) | The first reason was invented; the second is the §4 reason |
| 10 | Traits: "Fast scanner / Careful shopper / Bargain hunter" | "Expert / First-time user / Impatient mobile user" | ONE trait system (§4) |
| 11 | Feelings as stars/scores/paraphrases | The 3 §4 quotes, verbatim, attributed | Feelings are quotes, never scores (R2) |
| 12 | P2 chip: "5 screenshots · re-checked ✓" | "Proof attached · re-checked ✓" | No count exists for P2 — do not invent one |
| 13 | Sign-in button that opens the test report | Sign-in routes to real sign-in (or inert in a demo) | A control must do what its label says |
| 14 | Tabs 38px tall; grey text `#777777` | Tabs min-height 44px; faintest text `#6E6A5E` | 44px target rule + AA contrast (§11) |
| 15 | Gradients / glass loader / rainbow charts "to make it lively" | Flat bands, ink, status colours only | Decoration that carries no meaning is rejected (§12) |
| 16 | Arrows/funnel joining the 3 triptych panels | Panels independent; "Put together" strip BELOW does the joining | Testers are independent — that is the product claim (§5) |
| 17 | Footer with a Design-Notes block and no credit | No Design-Notes block; bottom bar: "© 2026 MarketTwin · Concept design" / "Developed by SJ" | §6 item 11 / §13 exception — the credit line IS production |
| 18 | "Needs your help" badge always visible | Badge ONLY when ≥1 tester is blocked | §3 badge rule |
| 19 | Netting change into "+1 improvement" | Three chips: "2 fixed" / "1 still broken" / "1 new" | Netting hides a still-broken problem |
| 20 | Building the Pages switcher / state switcher from the prototype | Real routes + real data-driven states (§13, §0A) | Those were review tools, not product |

**Final instruction to the implementing agent:** build in §14 order, check against §15/§15A as you finish each view (not only at the end), and if anything in the real repo makes a rule above impossible, STOP on that item and report it — a reported blocker is a success; a silent workaround is a failure.

— End of specification —

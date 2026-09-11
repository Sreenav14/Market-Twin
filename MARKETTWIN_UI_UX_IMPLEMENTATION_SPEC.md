.p# MarketTwin V1 UI/UX Design & Implementation Specification

**Status:** UI implementation plan after backend Step 17  
**Target codebase:** `apps/web`  
**Frontend:** React 19 + TypeScript + Vite + Tailwind CSS 4  
**Design system direction:** shadcn-compatible primitives + MarketTwin-specific product design  
**Primary goal:** Turn the current functional shell into a production-quality, evidence-first agentic testing interface that feels intentional, trustworthy, fast, and distinctly MarketTwin—not like generic “AI dashboard” UI.

---

# 1. Executive Summary

MarketTwin already has a real frontend foundation. We should **not rebuild the frontend from scratch**.

The current repository already has:

- React 19.
- TypeScript in strict mode.
- Vite.
- Tailwind CSS 4 via `@tailwindcss/vite`.
- React Router.
- Playwright E2E setup.
- Vitest.
- Axe accessibility tooling.
- An existing `src/components/ui` folder.
- A persistent application shell, sidebar, top bar, application pages, target pages, run routes, settings routes, and a New Study form.
- A real Control API client.
- A real backend results endpoint:
  - `GET /api/v1/test-runs/{test_run_id}/results`
- Existing backend data for deterministic findings and reports.

The frontend is therefore at the right moment for a **design-system upgrade and real result integration**, not a rewrite.

The most important UI decision is this:

> MarketTwin should look like an evidence and product-research instrument—not like an AI chat app and not like a template marketplace landing page.

The visual identity should be built around:

- journeys,
- perspectives,
- mission coverage,
- traces,
- evidence,
- observation,
- confidence,
- friction,
- reproduction,
- status,
- product insight.

The animated/shader references supplied by the project are useful, but they should be used selectively. A full-screen animated hero is suitable for:

- login,
- onboarding,
- an empty workspace,
- a polished public landing page,
- possibly the first “Create Study” experience.

It should **not** become the background of dense run-results pages.

The primary authenticated MarketTwin UI should feel closer to a sophisticated observability/research product: calm, information-dense when necessary, highly legible, strong interaction feedback, and clear evidence provenance.

---

# 2. Research Basis

This specification combines three kinds of input.

## 2.1 Existing MarketTwin codebase

The recommendations are grounded in the current branch:

`refactor/python-browser-controller`

Important current frontend facts:

- `apps/web/package.json` already includes React 19.1.1, React DOM 19.1.1, React Router DOM 7.18.2, Tailwind 4.3.3, TypeScript 7.0.2, Vite 8.2.2, Vitest, Playwright, Testing Library, and Axe.
- `apps/web/vite.config.ts` already uses:
  - `@vitejs/plugin-react`
  - `@tailwindcss/vite`
- `apps/web/src/styles.css` already begins with:
  - `@import "tailwindcss";`
- `src/components/ui` already exists.
- The app uses a dark persistent sidebar and a light content area.
- Many run subpages currently exist only as placeholder `FutureStagePage` screens.
- `RunLayout.tsx` currently disables perspectives, missions, journeys, activity, findings, evidence, and report tabs.
- `RunOverviewPage.tsx` contains stale copy saying planning is not connected.
- `NewRunPage.tsx` is already connected to real targets, authorization state, and Test Run creation.
- `api.ts` currently supports run creation/list/get but does not yet include the new results endpoint.

## 2.2 LinklyAI best-skills research

Source reviewed:

`https://github.com/LinklyAI/best-skills`

As of the reviewed ranking dated September 10, 2026, relevant highly ranked skills include:

- `frontend-design` by Anthropic.
- `vercel-react-best-practices` by Vercel Labs.
- `web-design-guidelines` by Vercel Labs.

The useful design conclusions from those referenced skills are:

1. Choose an aesthetic direction deliberately before implementation.
2. Ground the visual language in the subject matter.
3. Typography, spacing, color, motion, and composition must be intentional.
4. Avoid default “AI-generated” visual clichés.
5. Build production-grade React rather than static mockups.
6. Keep accessibility and interaction behavior part of the design system itself.
7. Optimize React rendering, fetching, and bundle behavior as part of UI quality.

These principles strongly support a MarketTwin-specific visual identity instead of copying a generic dashboard template.

## 2.3 Vercel Web Interface Guidelines

Reviewed source:

`https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`

Important rules incorporated into this spec:

- use semantic HTML before ARIA;
- icon-only controls require accessible names;
- every form control needs a real label or `aria-label`;
- focus must remain visible;
- sticky UI must not obscure focused elements;
- do not remove outlines without a real replacement;
- form errors should be next to the relevant field;
- async changes should use an appropriate live region;
- honor `prefers-reduced-motion`;
- animate transform/opacity where possible;
- do not use `transition: all`;
- long content must not destroy layouts;
- empty arrays/strings require real empty states;
- stateful filters/tabs should be reflected in URLs where appropriate;
- destructive actions need confirmation or undo;
- links are navigation, buttons are actions;
- active/hover/focus states should become more prominent;
- button text should describe the action precisely;
- dates/numbers should use `Intl.*`;
- meaningful images require alt text;
- large data lists may need virtualization.

## 2.4 shadcn/ui + Tailwind 4 research

The existing project already satisfies the major framework requirements:

- React: yes.
- TypeScript: yes.
- Tailwind CSS 4: yes.
- Vite: yes.

What it does **not** currently have:

- shadcn project configuration;
- `@/*` path alias;
- `cn()` helper;
- `lucide-react`;
- shadcn primitive components;
- standardized component variants;
- a clean semantic color-token layer.

The official Vite shadcn flow expects:

- Tailwind via `@tailwindcss/vite`;
- `@/*` alias;
- shadcn initialization;
- components under `src/components/ui`.

MarketTwin already uses that component folder, which is ideal.

## 2.5 21st.dev references

Reviewed:

- Animated Shader Hero discovery pages.
- Hero animation collections.
- Shader component collections.
- The supplied “Aero Hero” style code and the animated shader direction.

The useful ideas are:

- atmospheric motion can make the first impression feel premium;
- strong grid overlays can reinforce a technical identity;
- action buttons can have richer microinteraction than default rectangles;
- foreground typography can remain simple while the background carries character;
- shader effects should be restrained and should degrade gracefully.

However, these references are primarily **marketing/hero compositions**.

They should influence MarketTwin’s:

- login page,
- public marketing page,
- empty/new-study state,
- lightweight celebratory report completion state.

They should **not** dictate the information architecture of the core product.

---

# 3. Current Frontend Audit

## 3.1 What is already good

The current app has several strong architectural decisions.

### Persistent shell

`AppShell.tsx` already provides:

- workspace navigation;
- user identity;
- application-level sidebar;
- local environment indication;
- a central content area.

Keep this.

### Route architecture

The current route tree already anticipates most of the V1 product:

- Overview
- Applications
- Targets
- Runs
- Run Overview
- Perspectives
- Missions
- Journeys
- Activity
- Findings
- Evidence
- Report
- Human Action
- Settings

This is excellent because UI work can focus on implementation rather than route restructuring.

### Product terminology

The current code already uses the right product nouns:

- Study
- Target
- Perspectives
- Missions
- Journeys
- Findings
- Evidence

Do not rename these casually.

### Existing state utilities

The frontend already has:

- loading state patterns;
- error state patterns;
- authorization-aware screens;
- workspace permission checks.

These should be improved, not replaced unnecessarily.

---

# 4. Current Frontend Problems

## 4.1 The visual layer is too monolithic

`src/styles.css` is currently a large hand-written stylesheet containing:

- layout;
- buttons;
- forms;
- cards;
- sidebar;
- tabs;
- statuses;
- study composer;
- settings;
- run lifecycle;
- responsive behavior.

This creates several problems:

- UI variants become hard to reason about.
- Component behavior and appearance are separated.
- Visual consistency will drift as more complex result pages are added.
- It is harder to use accessible primitives consistently.
- It increases the chance of one-off CSS.

### Direction

Move toward:

- Tailwind utilities inside components;
- shadcn primitives for low-level UI;
- CSS variables/tokens for theme;
- small global CSS only for:
  - tokens,
  - base typography,
  - background behavior,
  - animation primitives,
  - genuinely global utilities.

Do **not** rewrite every current screen in one commit.

Use progressive migration.

---

## 4.2 The Run UI is stale relative to the backend

`RunOverviewPage.tsx` currently says:

> “Planning is not connected yet.”

That is no longer true.

The backend now supports:

- planning;
- personas;
- missions;
- journeys;
- browser execution;
- evidence;
- deterministic evaluation;
- cross-persona findings;
- deterministic reports;
- API retrieval of final results.

This stale copy should be removed immediately when UI integration starts.

---

## 4.3 Run tabs are artificially disabled

`RunLayout.tsx` currently renders almost all run tabs as disabled spans.

The desired target state is:

- Overview — always available.
- Perspectives — available after planning data is retrievable.
- Missions — available after planning data is retrievable.
- Journeys — available after planning data is retrievable.
- Activity — available once run events API exists.
- Findings — available when results exist.
- Evidence — available when artifact API exists.
- Report — available when results exist.
- Human Action — normally hidden; surfaced contextually only when intervention is required.

Do not leave a permanent row of disabled future tabs in the final product.

---

# 5. Product Design Positioning

## 5.1 What MarketTwin is visually

MarketTwin is not:

- ChatGPT with a sidebar;
- a generic analytics dashboard;
- a purple-gradient AI landing page;
- a card grid where every section has the same weight;
- a “glassmorphism everywhere” application;
- a developer terminal disguised as a user product.

MarketTwin should feel like:

> A research instrument that sends distinct simulated users through a product, records exactly what happened, and turns repeatable evidence into product decisions.

Use that sentence to evaluate every major UI decision.

---

# 6. Design Direction: “Evidence Lab”

Recommended design name:

## Evidence Lab

Visual characteristics:

- dark graphite navigation shell;
- bright, quiet workspace canvas;
- thin structural dividers;
- high information clarity;
- deliberate use of monospace for IDs, timestamps, actions, URLs, and trace data;
- strong but restrained color coding;
- subtle technical grid/trace motif;
- animated “signal” only where the system is actively doing work;
- evidence thumbnails that feel inspectable rather than decorative;
- persona identity through typography/iconography and small accent treatments;
- strong differentiation between:
  - fact,
  - model interpretation,
  - policy event,
  - system failure,
  - human action.

This direction is more ownable than “AI gradient dashboard.”

---

# 7. Anti-“AI Slop” Rules

These rules should be treated as product requirements.

## 7.1 Avoid generic visual clichés

Do not default to:

- giant purple/blue blurred gradient blobs;
- floating glass cards for every section;
- gradient text on every heading;
- sparkle/star icons next to every AI feature;
- robot heads;
- magic-wand icon overload;
- excessive pill shapes;
- “AI-powered” labels repeated everywhere;
- arbitrary 3D shapes with no product meaning;
- every panel having the same rounded-card treatment;
- every page using a hero block.

## 7.2 Make the domain visible

Use visual motifs tied to MarketTwin:

- route/journey lines;
- timeline traces;
- persona lanes;
- evidence pins;
- linked finding ↔ journey relationships;
- mission coverage;
- observed step sequences;
- reproducibility counts;
- run lifecycle;
- screenshots;
- policy boundaries.

## 7.3 Vary layout by task

The following pages should not all look like the same card grid:

- Findings → triage/list.
- Journey Detail → timeline.
- Evidence → visual gallery + metadata.
- Report → document/reading layout.
- Mission coverage → matrix.
- Personas → comparative profiles.
- Run Overview → command center.
- New Study → focused composer.

The information structure should determine composition.

---

# 8. What To Do With the Supplied Aero Hero Component

The supplied `aero-hero-3.tsx` and `demo.tsx` should be treated as **reference material**, not blindly inserted into the authenticated dashboard.

## 8.1 Good ideas to keep

- structured full-viewport composition;
- subtle vertical grid;
- strong headline hierarchy;
- simple body copy;
- one clear action;
- CTA microinteraction;
- Lucide icon usage;
- restrained foreground content.

## 8.2 Things that should not be copied directly

The sample’s:

- generic sustainability photo;
- green sustainability palette;
- marketing copy;
- full-screen hero height;
- always-present photographic background.

Those are unrelated to MarketTwin.

## 8.3 Correct MarketTwin adaptation

Use the same compositional idea for the **Login / First Workspace / New Study introductory state**:

Background:

- animated shader or soft generative field;
- very dark charcoal/ink;
- faint vertical technical grid;
- optional subtle cursor-reactive glow;
- no stock image required.

Foreground:

**Headline**
> See your product through more than one user.

**Supporting copy**
> MarketTwin plans distinct user perspectives, runs evidence-backed product journeys, and surfaces repeatable friction before your customers do.

**Primary action**
> Open Workspace

or when already authenticated:

> Create Study

Secondary metadata:

- “Evidence-backed”
- “Authorized targets only”
- “Human-assisted auth”

Do not show fake customer counts, fake company logos, fake results, or fake testimonials.

---

# 9. Animated Shader Hero Recommendation

The 21st.dev Animated Shader Hero reference is stylistically relevant because MarketTwin is an agentic product.

Use it carefully.

## Recommended placements

### A. Login screen

Strong recommendation.

Why:

- visual impact is useful here;
- little competing information;
- user has not entered the work surface yet;
- animation communicates the “simulated perspectives / moving system” idea.

### B. Empty workspace state

Possible.

Use a smaller contained shader field rather than full viewport.

### C. New Study composer

Possible, but subtle.

For example:

- 280–360 px decorative right panel on desktop;
- not behind the textarea;
- disabled or simplified on mobile.

### D. Run execution state

Do **not** use a hero.

Instead use a small “live signal” region:

- animated route line;
- active persona chip;
- subtle moving scanning gradient;
- progress rail.

### E. Result/report screens

No shader.

The results must feel stable, trustworthy, and inspectable.

---

# 10. shadcn Compatibility Upgrade

The project does not need Tailwind or TypeScript installed—they already exist.

It needs shadcn compatibility.

## 10.1 Current status

### React
Already installed.

### TypeScript
Already installed and strict.

### Tailwind
Already Tailwind 4.

### `src/components/ui`
Already exists.

This is the correct standard component location.

### Missing
- shadcn configuration;
- `@` alias;
- `cn()` utility;
- Lucide;
- class variant utilities;
- animation package;
- standardized primitives.

---

# 11. Step-by-Step shadcn Setup

Run from:

```bash
cd apps/web
```

## 11.1 Install core supporting dependencies

```bash
npm install \
  lucide-react \
  clsx \
  tailwind-merge \
  class-variance-authority \
  tw-animate-css
```

Some shadcn components will install additional Radix dependencies automatically when added.

## 11.2 Add `@/*` alias to TypeScript

Current `tsconfig.json` does not define it.

Add inside `compilerOptions`:

```json
{
  "baseUrl": ".",
  "paths": {
    "@/*": ["./src/*"]
  }
}
```

Keep all existing strict TypeScript configuration.

## 11.3 Add alias to Vite

Update `apps/web/vite.config.ts`:

```ts
import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

## 11.4 Create `cn()`

Create:

`apps/web/src/lib/utils.ts`

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

## 11.5 Initialize shadcn

Run:

```bash
npx shadcn@latest init
```

Recommended answers:

- Style: `New York`
- Base color: Neutral
- CSS variables: yes
- Global CSS: `src/styles.css`
- Components: `src/components`
- Utilities: `src/lib/utils.ts`

Verify that the tool does not replace MarketTwin-specific styles unexpectedly.

Review the diff before committing.

## 11.6 Add initial primitives

Do not install 30 components on day one.

Start with:

```bash
npx shadcn@latest add \
  button \
  badge \
  card \
  separator \
  tabs \
  tooltip \
  dropdown-menu \
  skeleton \
  alert \
  dialog \
  sheet \
  scroll-area \
  progress \
  table
```

Soon after:

```bash
npx shadcn@latest add \
  input \
  textarea \
  select \
  form \
  command \
  breadcrumb \
  avatar \
  sonner
```

Potential later components:

- resizable;
- popover;
- calendar;
- collapsible;
- hover-card.

---

# 12. Important Correction to the Supplied Tailwind Theme Code

Do **not** paste the supplied CSS block unchanged.

It contains references such as:

```css
var(----ring)
var(----input)
var(----border)
```

Those are invalid for the intended token names.

They should be:

```css
var(--ring)
var(--input)
var(--border)
```

The supplied block also references tokens that are not fully defined in its own `:root`.

MarketTwin should use a complete token layer rather than partially patching variables.

---

# 13. Recommended Tailwind 4 Theme Foundation

Keep:

```css
@import "tailwindcss";
@import "tw-animate-css";
```

Then gradually replace the current enormous global rule set with semantic tokens.

A recommended starting direction:

```css
@import "tailwindcss";
@import "tw-animate-css";

@custom-variant dark (&:is(.dark *));

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);

  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);

  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);

  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);

  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);

  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);

  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);

  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);

  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);

  --color-info: var(--info);
  --color-info-foreground: var(--info-foreground);
  --color-success: var(--success);
  --color-success-foreground: var(--success-foreground);
  --color-warning: var(--warning);
  --color-warning-foreground: var(--warning-foreground);

  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) + 4px);
}

:root {
  --radius: 0.75rem;

  --background: oklch(0.982 0.004 270);
  --foreground: oklch(0.19 0.015 270);

  --card: oklch(1 0 0);
  --card-foreground: oklch(0.19 0.015 270);

  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.19 0.015 270);

  --primary: oklch(0.57 0.19 267);
  --primary-foreground: oklch(0.985 0 0);

  --secondary: oklch(0.955 0.008 270);
  --secondary-foreground: oklch(0.26 0.018 270);

  --muted: oklch(0.955 0.008 270);
  --muted-foreground: oklch(0.50 0.02 270);

  --accent: oklch(0.94 0.03 180);
  --accent-foreground: oklch(0.23 0.04 180);

  --destructive: oklch(0.60 0.20 25);
  --destructive-foreground: oklch(0.45 0.17 25);

  --border: oklch(0.90 0.008 270);
  --input: oklch(0.90 0.008 270);
  --ring: oklch(0.57 0.19 267);

  --info: oklch(0.62 0.15 245);
  --info-foreground: oklch(0.42 0.15 245);

  --success: oklch(0.62 0.15 155);
  --success-foreground: oklch(0.40 0.12 155);

  --warning: oklch(0.72 0.16 75);
  --warning-foreground: oklch(0.46 0.13 65);
}

.dark {
  --background: oklch(0.15 0.012 270);
  --foreground: oklch(0.96 0.004 270);

  --card: oklch(0.19 0.014 270);
  --card-foreground: oklch(0.96 0.004 270);

  --popover: oklch(0.19 0.014 270);
  --popover-foreground: oklch(0.96 0.004 270);

  --primary: oklch(0.70 0.16 267);
  --primary-foreground: oklch(0.15 0.012 270);

  --secondary: oklch(0.24 0.014 270);
  --secondary-foreground: oklch(0.94 0.004 270);

  --muted: oklch(0.24 0.014 270);
  --muted-foreground: oklch(0.70 0.018 270);

  --accent: oklch(0.28 0.04 180);
  --accent-foreground: oklch(0.90 0.05 180);

  --destructive: oklch(0.66 0.19 25);
  --destructive-foreground: oklch(0.78 0.15 25);

  --border: oklch(1 0 0 / 10%);
  --input: oklch(1 0 0 / 12%);
  --ring: oklch(0.70 0.16 267);

  --info: oklch(0.68 0.14 245);
  --info-foreground: oklch(0.77 0.11 245);

  --success: oklch(0.68 0.14 155);
  --success-foreground: oklch(0.78 0.10 155);

  --warning: oklch(0.75 0.15 75);
  --warning-foreground: oklch(0.82 0.11 75);
}
```

These exact values may be tuned during visual implementation.

The important decision is the **semantic token structure**.

---

# 14. Color Semantics

Do not use color decoratively without meaning.

Recommended semantic meanings:

| Color | Meaning |
|---|---|
| Primary indigo/cobalt | product action / selected / active |
| Cyan/teal | evidence / observation / trace |
| Green | passed / verified / healthy |
| Amber | friction / partial / caution |
| Red | failed / blocker / destructive |
| Neutral gray | pending / unknown / inactive |
| Violet only if needed | persona/model-generated interpretation |

Avoid making “AI” itself purple.

---

# 15. Typography

Typography is one of the easiest ways to avoid generic UI.

## 15.1 Recommended type roles

### Interface / reading font

Choose one modern, highly readable variable sans and use it consistently.

Candidates:

- Instrument Sans
- IBM Plex Sans
- Geist Sans only if simplicity is preferred over distinctiveness

Recommended:

**Instrument Sans**

Why:

- clean enough for enterprise UI;
- less default-looking than Inter;
- strong at medium/semibold weights;
- good compact dashboard rhythm.

### Technical/data font

Use:

**IBM Plex Mono**

for:

- Run IDs;
- URLs;
- artifact keys;
- execution steps;
- timestamps;
- policy codes;
- action names;
- trace metadata.

Do not use monospace for general body text.

## 15.2 Type scale

Suggested:

- Display/hero: `clamp(3rem, 7vw, 6rem)`
- Page title: 32–40 px
- Section title: 20–24 px
- Panel title: 15–18 px
- Body: 14–16 px
- Secondary: 13–14 px
- Metadata: 11–12 px
- Technical metadata: 11–13 px mono

Avoid tiny 9–10 px text for important information.

The current UI frequently uses 9.5–11 px. That should be reserved for metadata, not key controls or content.

---

# 16. Radius, Borders, and Elevation

Avoid every object looking like a floating rounded rectangle.

Recommended hierarchy:

### Main content surfaces
- radius: 16 px
- very subtle border
- little or no shadow

### Interactive cards
- radius: 12–14 px
- hover border/contrast change
- optional subtle shadow on hover

### Inputs
- radius: 10–12 px

### Pills/badges
- full radius only when semantically appropriate

### Dense tables/timelines
- mostly border/divider based
- minimal card wrapping

### Modals/sheets
- 16–20 px radius

Use shadows sparingly.

A serious research product should rely more on structure, spacing, and contrast than floating shadows.

---

# 17. Motion System

Motion should explain state.

## 17.1 Motion categories

### System-active motion

Use when MarketTwin is actively working.

Examples:

- subtle moving signal line;
- progress indicator;
- current Journey pulse;
- active browser step indicator.

### Spatial motion

Use for:

- sheet opening;
- detail transitions;
- dropdown;
- command menu.

### Feedback motion

Use for:

- successful copy;
- saved change;
- finding selected;
- evidence linked.

### Atmospheric motion

Only:

- login;
- empty/new-study experience.

## 17.2 Rules

- respect `prefers-reduced-motion`;
- avoid `transition: all`;
- prioritize transform and opacity;
- never animate large background effects behind dense text;
- do not make result tables continuously move;
- no infinite “AI sparkle” animation;
- no loading spinner if skeleton/progress provides better context.

---

# 18. Responsive Strategy

MarketTwin is desktop-first because:

- evidence inspection;
- Journey timelines;
- screenshots;
- report comparison;
- table-like data

benefit from space.

But it must remain usable on smaller screens.

## Breakpoints

### Desktop ≥ 1280
- persistent sidebar;
- 2–3 column overview layout;
- evidence side-by-side;
- wide Journey timeline.

### Laptop 1024–1279
- narrower sidebar;
- mostly two-column;
- activity metadata collapses.

### Tablet 768–1023
- sidebar becomes collapsible Sheet;
- one-column details;
- horizontal tabs scroll;
- evidence panel stacks.

### Mobile < 768
- sidebar hidden behind menu;
- page header stacks;
- tables become row cards when required;
- no full shader performance-heavy scene;
- persistent bottom actions only when essential;
- minimum interaction target 44 px preferred, never below accessibility minimum.

---

# 19. Information Architecture

The existing route architecture should largely remain.

## Global

- Overview
- Applications
- Runs
- Settings

## Application

- Application Overview
- Targets
- Runs

## Target

- Overview
- Authorization
- Network Policy

## Run

- Overview
- Perspectives
- Missions
- Journeys
- Activity
- Findings
- Evidence
- Report

Human Action is contextual and should not feel like a permanent top-level report tab.

---

# 20. Global App Shell Redesign

Keep the dark sidebar/light workspace concept.

Improve it.

## 20.1 Sidebar

Width:

- 240–256 px expanded.
- future collapsed state optional.

Top:

- MarketTwin brand.
- workspace switcher.

Primary nav:

- Overview
- Applications
- Runs

Bottom:

- Settings
- user menu

Use Lucide icons consistently.

Suggested icons:

- Overview → `LayoutDashboard`
- Applications → `Boxes`
- Runs → `Waypoints` or `Route`
- Settings → `Settings2`
- Target → `Globe2`
- Evidence → `ScanSearch`
- Findings → `TriangleAlert`
- Report → `FileText`
- Personas → `UsersRound`
- Missions → `Goal`
- Journeys → `Route`

Avoid custom one-off SVG icons unless branding requires them.

## 20.2 Top bar

Current breadcrumb generated from URL text is too mechanical.

Replace with semantic breadcrumbs:

```text
Applications / Checkout App / Study / Pricing comprehension
```

Top-right:

- environment indicator;
- global command/search later;
- help;
- account dropdown.

Do not waste the topbar on decorative elements.

## 20.3 Skip link

Add a “Skip to main content” link that appears on keyboard focus.

The `<main id="main-content">` already exists, so this is straightforward.

---

# 21. Command Palette

Recommended after base UI is stable.

Keyboard:

`⌘K` / `Ctrl+K`

Actions:

- Go to Applications
- Go to Runs
- Create Study
- Open recent Study
- Search finding title
- Search Run ID

This improves repeated use for expert users.

Do not implement global AI chat as the primary navigation mechanism.

---

# 22. New Study Experience

This is one of the most important screens because it expresses the product promise.

Current `NewRunPage.tsx` already has strong logic.

Preserve:

- authorized-target filtering;
- target selection;
- study brief;
- length validation;
- permission state.

Redesign the composition.

## Desktop target

Two-column composition:

```text
┌──────────────────────────────────────┬─────────────────────┐
│ Study composer                       │ Ambient signal      │
│                                      │ / guidance          │
│ What do you want to learn?           │                     │
│                                      │ MarketTwin will     │
│ Target [ Checkout Prod ▼ ]           │ generate 3          │
│                                      │ perspectives and    │
│ ┌──────────────────────────────────┐ │ missions from       │
│ │ Can first-time customers...     │ │ this brief.         │
│ │                                  │ │                     │
│ └──────────────────────────────────┘ │ subtle shader       │
│                                      │ field               │
│ Good study prompt hints              │                     │
│                         Create Study │                     │
└──────────────────────────────────────┴─────────────────────┘
```

The right panel can incorporate the animated shader visual language.

## Do not over-prompt

Users should not be forced to write a complicated prompt.

Use three small examples:

- “Can first-time buyers understand our pricing?”
- “Can returning users reorder quickly?”
- “Do teams understand permission settings?”

Clicking an example may fill the input.

## Study brief copy

Use:

> Describe the decision or outcome you want to understand. MarketTwin will create the perspectives and missions.

Do not say:

> Enter an AI prompt.

---

# 23. Run Overview — Target Experience

This should become the main “command center.”

## 23.1 Header

Left:

- Study title derived from brief.
- target + environment.
- created time.
- run status.

Right:

Context-dependent action.

Draft:
- `Start Study` once backend supports it.

Running:
- `Cancel Run` eventually.

Completed:
- `View Report`

## 23.2 Lifecycle rail

Replace the simplistic four-block bar with a more informative lifecycle:

1. Created
2. Planning
3. Running
4. Evaluating
5. Ready

Each stage:

- icon;
- label;
- timestamp when available;
- active state.

Do not animate every completed stage.

## 23.3 Completed overview metrics

Recommended metrics:

- Perspectives
- Missions
- Journeys
- Passed
- Partial
- Failed
- Findings
- High/Critical findings

Do not make 8 equal cards.

Use hierarchy.

Example:

```text
Outcome
68% journey success

6 Journeys
4 Passed
1 Partial
1 Failed
```

Then separate finding summary.

## 23.4 Top findings

Show max 3.

Each finding row:

- severity;
- title;
- affected perspectives count;
- evidence count;
- “Open finding”.

## 23.5 Recent activity

Compact timeline.

Examples:

- Persona “Cautious Buyer” started Checkout mission
- Navigation completed
- Journey marked partial
- Finding generated
- Report ready

---

# 24. Perspectives Page

Purpose:

> Help a product team understand whose eyes MarketTwin used.

Do not make personas cartoon avatars.

Recommended card:

```text
Cautious First-Time Buyer
─────────────────────────
Perspective
Wants to understand cost before commitment.

Behavior
• reads comparison copy
• hesitates on ambiguous recurring charges
• avoids irreversible actions

Priorities
Clarity • reversibility • trust

Journeys
2 passed · 1 partial
```

Visual identity:

- typographic;
- small generated monogram/avatar;
- one restrained accent per persona;
- no human stock photos;
- no fake demographic portraits.

Reason:

Personas are behavioral simulations, not fake literal humans.

---

# 25. Missions Page

Mission UI should feel outcome-oriented.

Each mission shows:

- mission name;
- objective;
- priority;
- success criteria;
- coverage.

Add matrix:

| Mission | Persona A | Persona B | Persona C |
|---|---|---|---|
| Understand pricing | Pass | Partial | Fail |
| Find cancellation | Pass | Pass | Pass |

This is one of the highest-value views in the product.

It visually exposes repeated problems without requiring the user to read every Journey.

---

# 26. Journeys Page

Primary view:

a filterable list/table.

Columns:

- Persona
- Mission
- Status
- Outcome
- Steps
- Friction
- Final URL
- Duration when available

Filters:

- outcome;
- persona;
- mission;
- status.

Filters should be URL-backed.

Example:

`?outcome=failed&persona=cautious_buyer`

This supports sharing/reloading.

## Row interaction

Whole row can be visually hoverable, but navigation should use a real link.

Avoid `<div onClick>`.

---

# 27. Journey Detail Page

This should be one of MarketTwin’s strongest screens.

Layout:

```text
┌──────────────────────────┬──────────────────────────────┐
│ Journey timeline         │ Evidence inspector           │
│                          │                              │
│ 01 Navigate              │ screenshot                   │
│    /pricing              │                              │
│                          │ metadata                     │
│ 02 Click                 │                              │
│    “Compare plans”       │ console/network badges       │
│                          │                              │
│ 03 Scroll                │                              │
│                          │                              │
│ 04 Click                 │                              │
│    “Start Trial”         │                              │
└──────────────────────────┴──────────────────────────────┘
```

## Timeline step

Each step:

- sequence number;
- action;
- concise action summary;
- URL;
- status;
- time if available;
- evidence indicator.

The timeline is authoritative execution truth.

Make that visually explicit:

**Observed execution**

not:

**AI reasoning**

## Persona interpretation block

Separate section:

**Persona conclusion**

- outcome;
- summary;
- friction;
- blockers;
- satisfied criteria;
- unsatisfied criteria.

This separation is important because MarketTwin’s architecture deliberately distinguishes browser truth from persona interpretation.

---

# 28. Findings Page

This is arguably the most important commercial screen.

It should answer:

1. What should I care about?
2. How serious is it?
3. How repeatable is it?
4. Who experienced it?
5. What evidence supports it?
6. What should I do next?

## Layout

Top toolbar:

- search;
- severity filter;
- category filter;
- affected persona filter;
- sort.

Default sorting:

1. Critical
2. High
3. Medium
4. Low
5. Info

Then repeatability/affected Journey count.

## Finding list item

```text
HIGH
Checkout completion failed

2 of 3 perspectives failed to reach the confirmation state.

Affected
Cautious Buyer · Busy Returning User

Evidence
2 screenshots · 2 Journey traces

Recommendation
Review the disabled Continue state and validation feedback.

[Open Finding]
```

Do not make the severity badge the largest visual element.

The finding title should dominate.

---

# 29. Finding Detail Page

Recommended structure:

## Header

- severity;
- title;
- category;
- status.

## Summary

Plain-language explanation.

## Reproduction

Show:

- affected Journeys;
- persona;
- mission;
- outcome.

## Evidence

Side-by-side evidence cards.

## Recommendation

Clear next action.

## Provenance

Small section:

- deterministic rule;
- created at;
- linked execution;
- linked step/artifact IDs.

This dramatically increases trust.

---

# 30. Evidence Page

Evidence must not look like a generic file manager.

Use evidence type tabs:

- Screenshots
- Traces
- Accessibility
- Console
- Network

## Screenshot grid

Cards:

- screenshot preview;
- Journey;
- step;
- action;
- timestamp.

Use fixed aspect containers to prevent layout shift.

Below-fold images should lazy load.

## Trace item

Do not attempt to reimplement Playwright Trace Viewer initially.

Provide:

- trace metadata;
- related execution;
- secure open/download action later.

## Accessibility snapshot

Render as structured text/tree only if useful.

Do not dump a huge YAML block by default.

---

# 31. Report Page

The Report page should feel like a document, not another dashboard.

Use a centered reading column with optional sticky table of contents.

Sections:

1. Executive Summary
2. Run Coverage
3. Outcome Summary
4. Priority Findings
5. Cross-Persona Patterns
6. Mission Coverage
7. Recommendations
8. Method & Evidence

Top actions:

- Copy summary
- Export later
- Share later

No giant animated hero.

No cards around every paragraph.

---

# 32. Activity Page

The Activity page is an operational event timeline.

Examples:

```text
10:42:05  Planning started
10:42:12  3 perspectives created
10:42:13  4 missions created
10:42:18  Journey 1/12 started
10:42:21  Browser navigated to /pricing
10:43:02  Journey completed
...
```

Use tabular numerals.

Filters:

- all;
- system;
- execution;
- policy;
- evaluation;
- human action.

This page should feel closer to observability tooling.

---

# 33. Human Action UX

Human intervention should not be a generic modal that suddenly asks for a password.

## Entry state

Prominent but calm banner:

> Action needed to continue this Journey.

Explain:

- why MarketTwin paused;
- what the user needs to do;
- that the agent is paused;
- that evidence capture is paused for secret entry;
- that the same browser session will resume.

Example:

```text
Login required

MarketTwin reached an authenticated area.

The agent is paused.
Screenshot and trace capture are paused while you enter credentials.

[Take Control]
```

## Control state

- clear “You are controlling the browser” state;
- timer/lease if implemented;
- `Resume MarketTwin` action;
- no secret values echoed in MarketTwin UI.

## Resume confirmation

> Authentication verified. MarketTwin can continue.

This flow is important to trust.

---

# 34. Status Language

Use consistent words everywhere.

## Run status

- Draft
- Planning
- Queued
- Running
- Evaluating
- Completed
- Failed
- Cancelled

## Journey outcome

- Passed
- Partial
- Failed
- Inconclusive

## Policy

Do not visually merge policy blocks with product failures.

Policy blocked:

- separate category;
- shield icon;
- amber/neutral treatment.

This preserves the backend semantic separation already implemented.

---

# 35. Empty States

Every major section needs a meaningful empty state.

## No findings

Good:

> No evidence-backed issues were found in this run.

Support:

> Review the Journey coverage before concluding that the product has no usability problems.

Bad:

> Nothing here yet ✨

## No evidence

> This Journey did not produce an evidence artifact.

Show whether:

- execution did not run;
- capture was paused;
- artifact persistence failed.

## No runs

Use this as a stronger onboarding moment.

This is a good place for a small shader/visual motif.

---

# 36. Loading States

Do not use a global spinner for everything.

Use:

- skeletons for list pages;
- fixed geometry to avoid layout shift;
- progress state for active runs;
- inline spinner only for button submissions.

Button example:

- idle: `Create Study`
- active: `Creating…`

The supplied Vercel guidelines explicitly recommend the submit button only entering disabled/loading state once the request has started.

---

# 37. Error States

Errors should include next actions.

Bad:

> Request failed.

Good:

> Results are not available yet. The run has completed execution but evaluation is still finishing.

Action:

`Refresh Results`

Good:

> Target authorization has expired.

Action:

`Review Authorization`

Good:

> Evidence could not be loaded.

Actions:

- `Try Again`
- `Open Journey`

---

# 38. URL State

Use URL search params for:

- Findings filters.
- Journey filters.
- Evidence type.
- Activity filters.
- sorting.
- pagination.

This gives:

- shareable state;
- refresh persistence;
- back/forward support.

Do not hide major navigation state only in React `useState`.

---

# 39. Data Fetching Strategy

The current app uses a simple `useAsync`.

That is fine for now.

Do not introduce TanStack Query solely because it is popular.

Introduce it when the app actually needs:

- shared cache;
- polling;
- invalidation;
- mutations;
- background refresh;
- dependent queries.

MarketTwin will likely reach that point when worker wiring and live-run status are connected.

Recommended transition point:

When implementing:

- live run polling/SSE;
- results availability;
- retry/cancel;
- evidence refresh.

At that point, TanStack Query becomes justified.

---

# 40. Real Backend Data Available Now

The UI can already consume:

## Existing Run

```http
GET /api/v1/test-runs/{run_id}
```

## Existing final results

```http
GET /api/v1/test-runs/{run_id}/results
```

The results endpoint includes:

- report;
- executive summary;
- report payload;
- finding list;
- severity;
- category;
- title;
- summary;
- recommendation;
- Journey IDs;
- step IDs;
- artifact IDs.

This means the following pages can become real **now**:

- Run Overview — completed report summary.
- Findings — real findings.
- Finding Detail — partially real.
- Report — real report.

The following still need richer backend API support:

- Perspectives.
- Missions.
- Journeys.
- Journey Detail.
- Evidence gallery.
- Evidence Detail.
- Activity.

Do not fake these data sets in production UI.

---

# 41. Extend `api.ts`

Add result interfaces.

Example:

```ts
export interface FindingEvidence {
  step_ids: number[];
  artifact_ids: string[];
}

export interface Finding {
  id: string;
  severity: string;
  category: string;
  title: string;
  summary: string;
  recommendation: string | null;
  status: string;
  journey_ids: string[];
  evidence: FindingEvidence;
}

export interface RunReport {
  id: string;
  version: number;
  status: string;
  executive_summary: string | null;
  payload: Record<string, unknown>;
  generated_at: string | null;
}

export interface TestRunResults {
  test_run_id: string;
  report: RunReport;
  findings: Finding[];
}
```

Add:

```ts
getRunResults: (runId: string) =>
  request<TestRunResults>(
    `/api/v1/test-runs/${runId}/results`,
  ),
```

Do not use `any`.

---

# 42. Results API State Handling

`GET /results` can return:

## 200

Render results.

## 409 — run not complete

Render:

- lifecycle state;
- progress explanation;
- no error-red panel.

## 409 — evaluation unavailable

Render:

> Execution is complete. Evaluation is finishing.

This should feel like normal lifecycle behavior, not a failure.

## 404

User cannot access it or it does not exist.

Use a safe not-found state.

---

# 43. Recommended Component Architecture

## `src/components/ui`

Low-level reusable primitives.

Examples:

- `button.tsx`
- `badge.tsx`
- `card.tsx`
- `dialog.tsx`
- `sheet.tsx`
- `tooltip.tsx`
- `tabs.tsx`
- `table.tsx`
- `skeleton.tsx`
- `separator.tsx`
- `scroll-area.tsx`

These should remain generic.

## `src/components/markettwin`

Create this folder for product-specific components.

Recommended:

```text
src/components/markettwin/
  app-sidebar.tsx
  run-status.tsx
  run-lifecycle.tsx
  outcome-summary.tsx
  finding-list-item.tsx
  finding-severity.tsx
  evidence-thumbnail.tsx
  journey-timeline.tsx
  execution-step.tsx
  persona-card.tsx
  mission-coverage-matrix.tsx
  report-section.tsx
  empty-state.tsx
  human-action-banner.tsx
  signal-background.tsx
```

This distinction is important.

Do not put `JourneyTimeline` into generic `components/ui`.

---

# 44. Suggested Feature Organization

As the UI grows, consider:

```text
src/
  app/
  components/
    ui/
    markettwin/
  features/
    runs/
      api.ts
      types.ts
      components/
    findings/
      components/
    evidence/
      components/
    targets/
  layouts/
  pages/
  lib/
```

Do not perform this entire folder migration immediately.

Use it for new complex UI first.

---

# 45. Lucide Icon Rules

Use `lucide-react`.

Do not manually copy random SVG markup for standard actions.

Standardize sizes:

- inline metadata: 14 px
- normal controls: 16 px
- prominent section icon: 18–20 px
- empty state: 24–32 px

Icon-only button:

```tsx
<Button
  variant="ghost"
  size="icon"
  aria-label="Copy Run ID"
>
  <Copy aria-hidden="true" />
</Button>
```

Decorative icon:

```tsx
<ScanSearch aria-hidden="true" />
```

Never rely on icon shape alone for critical status.

---

# 46. Buttons

Recommended variants:

- default / primary
- secondary
- outline
- ghost
- destructive
- link

MarketTwin-specific state can wrap them, not fork Button internals.

Use specific labels:

Good:

- Create Study
- Start Study
- Open Finding
- View Evidence
- Retry Evaluation
- Take Control
- Resume MarketTwin

Bad:

- Continue
- Go
- Submit
- Next

unless context makes them absolutely obvious.

---

# 47. Data Density

Enterprise products often fail in one of two ways:

1. too much density;
2. gigantic low-density cards.

MarketTwin should use progressive detail.

### Level 1
Run overview:
- summary.

### Level 2
Finding/Journey list:
- compact comparison.

### Level 3
Detail page:
- complete evidence.

Do not put complete execution traces on the Run Overview.

---

# 48. Tables vs Cards

Use a table when users compare the same fields across many records.

Use cards when records contain heterogeneous narrative information.

Recommended:

### Table
- Runs
- Journeys
- Activity
- Mission × Persona matrix

### Card/list
- Perspectives
- Findings
- Evidence previews

### Document
- Report

---

# 49. Accessibility Target

Target:

**WCAG 2.2 AA**

Important requirements:

- visible focus;
- semantic controls;
- keyboard navigation;
- minimum target sizing;
- focus not hidden by sticky header;
- sufficient color contrast;
- no status communicated only by color;
- appropriate headings;
- labels;
- accessible error messages;
- motion reduction;
- modal focus management;
- screen reader live feedback for async actions.

Existing `@axe-core/playwright` is a strong foundation.

Use it.

---

# 50. Focus Design

Use one consistent focus treatment.

Example:

```text
2 px high-contrast ring
+ 2 px offset
```

Do not create different focus styles for every component.

Sticky topbar and future sticky detail rails must not obscure focused controls.

---

# 51. Keyboard Behavior

At minimum:

- sidebar links keyboard navigable;
- tabs keyboard navigable;
- modal/sheet focus trapped appropriately;
- Escape closes overlays;
- command palette keyboard driven;
- timeline controls do not require pointer;
- evidence viewer zoom controls keyboard accessible;
- filters accessible without drag.

---

# 52. Reduced Motion

Add global helper patterns.

Example concept:

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
  }

  .ambient-motion {
    animation: none !important;
  }
}
```

Do not indiscriminately remove every transition if feedback becomes confusing.

Provide a nonanimated equivalent.

---

# 53. Performance Rules

## Avoid heavy WebGL in the application shell

One shader on login is fine.

Five WebGL canvases across run pages are not.

## Lazy load rich visuals

If the shader component uses a heavy dependency, load it dynamically only where used.

## Evidence images

- explicit dimensions;
- lazy loading;
- thumbnails;
- do not request original full-resolution evidence for every grid tile.

## Large activity list

If >50–100 rows regularly:

- virtualization or `content-visibility`.

## Avoid unnecessary context rerenders

Do not put rapidly changing live-run state into the top-level AppShell context if it forces the entire application to rerender.

---

# 54. Testing Strategy

## Unit/component

Use Vitest + Testing Library for:

- status mapping;
- severity mapping;
- results response rendering;
- filtering;
- empty state logic;
- 409 results state;
- finding cards;
- report sections.

## Accessibility

Use:

- role-based Testing Library assertions;
- Axe in Playwright;
- keyboard smoke tests.

## E2E

Create flows:

### E2E A
Login → Application → New Study → Create Study.

### E2E B
Open completed Run → Findings → Finding Detail → Evidence reference.

### E2E C
Open Report → verify executive summary + severity counts.

### E2E D later
Human Action → Take Control → Resume.

---

# 55. Visual Regression

Recommended once the design stabilizes.

At minimum capture:

- Login desktop/mobile.
- Overview.
- New Study.
- Run Overview completed.
- Findings.
- Finding Detail.
- Journey Detail.
- Evidence.
- Report.

Avoid blocking early development on pixel-perfect snapshots.

---

# 56. UI Implementation Phases

The UI should be developed in small, real steps.

---

# Phase UI-1 — Foundation Upgrade

Goal:

Make the existing app shadcn-compatible without changing product behavior.

Tasks:

1. Add `@/*` alias.
2. Add `src/lib/utils.ts`.
3. Install:
   - lucide-react
   - clsx
   - tailwind-merge
   - class-variance-authority
   - tw-animate-css
4. Initialize shadcn.
5. Add initial shadcn primitives.
6. Add semantic Tailwind tokens.
7. Keep current pages working.
8. Add skip link.
9. Add reduced-motion baseline.
10. Begin replacing custom Icon with Lucide.

Definition of done:

- build passes;
- tests pass;
- existing screens still usable;
- no route broken;
- no major visual redesign yet.

---

# Phase UI-2 — App Shell & Core Components

Goal:

Create the final MarketTwin visual foundation.

Tasks:

1. Redesign sidebar.
2. Semantic breadcrumbs.
3. Standard PageHeader.
4. Standard StatusBadge.
5. Standard EmptyState.
6. Standard AsyncState wrapper.
7. Button migration.
8. Tooltip behavior.
9. Add `components/markettwin`.
10. Define:
    - RunStatus
    - Outcome
    - FindingSeverity

Definition of done:

- shell feels deliberate;
- navigation works desktop/mobile;
- no inaccessible icon buttons;
- semantic token usage replaces raw color usage in new components.

---

# Phase UI-3 — New Study Redesign

Goal:

Make creating a study feel like the start of MarketTwin, not a generic form.

Tasks:

1. Preserve existing backend logic.
2. Convert target selector to shadcn Select.
3. Improve textarea/composer.
4. Add examples.
5. Add study guidance.
6. Add optional contained ambient shader panel.
7. Improve loading/authorization empty states.
8. Maintain permission behavior.

Definition of done:

- no fake data;
- no fake progress;
- design communicates dynamic perspectives/missions;
- mobile works.

---

# Phase UI-4 — Results API Integration

Goal:

Use Step 17 backend immediately.

Tasks:

1. Add result TypeScript interfaces.
2. Add `api.getRunResults`.
3. Add result loader/hook.
4. Interpret 409 as lifecycle state.
5. Remove stale “planning not connected” copy.
6. Enable Findings tab when results available.
7. Enable Report tab when results available.
8. Implement real completed Run Overview.

Definition of done:

- completed Run renders real backend data;
- no placeholder numbers.

---

# Phase UI-5 — Findings

Goal:

Build MarketTwin’s primary insight workflow.

Tasks:

1. `FindingListItem`.
2. severity UI.
3. category rendering.
4. filtering.
5. sorting.
6. affected Journey count.
7. evidence count.
8. Finding Detail route.
9. provenance section.
10. copy recommendation action.

Definition of done:

- user can triage findings quickly;
- evidence relationships are visible;
- no finding is presented as unsupported opinion.

---

# Phase UI-6 — Report

Goal:

Render deterministic report cleanly.

Tasks:

1. executive summary;
2. Journey counts;
3. severity counts;
4. category counts;
5. priority finding sections;
6. readable report typography;
7. sticky section TOC on desktop;
8. copy summary.

Definition of done:

- report reads like a product research document;
- raw JSON is never the primary interface.

---

# Phase UI-7 — Planning Views

Blocked on or paired with richer Control API endpoints.

Build:

- Perspectives;
- Missions;
- Journey list;
- coverage matrix.

Do not mock production data.

---

# Phase UI-8 — Journey & Evidence Inspector

Blocked on detail APIs.

Build:

- authoritative execution step timeline;
- Journey persona conclusion;
- screenshot inspector;
- artifact metadata;
- accessibility snapshot;
- console/network views.

---

# Phase UI-9 — Live Activity

After event/SSE wiring:

- realtime lifecycle;
- current Persona/Mission;
- active Journey;
- current stage;
- event timeline.

Use motion only for current activity.

---

# Phase UI-10 — Human Control

After HITL backend wiring:

- action-needed banner;
- secure takeover UI;
- exact same context viewer;
- capture paused indicator;
- resume flow.

---

# 57. What We Should Build First

The first implementation step should **not** be the shader hero.

The correct order is:

1. shadcn compatibility;
2. semantic tokens;
3. shell;
4. real results API;
5. Run Overview;
6. Findings;
7. Report;
8. then atmosphere/hero polish.

Why:

If we lead with animation before the information architecture is strong, we will make something pretty but not useful.

---

# 58. Proposed First 5 UI Commits

## Commit 1

`prepare frontend design system`

Changes:

- alias;
- `cn`;
- shadcn init;
- Lucide;
- tokens;
- Button/Badge/Card/Skeleton/etc.

## Commit 2

`upgrade markettwin application shell`

Changes:

- sidebar;
- topbar;
- breadcrumbs;
- responsive Sheet;
- keyboard/focus improvements.

## Commit 3

`connect test run results to frontend`

Changes:

- TypeScript result types;
- `api.getRunResults`;
- state handling;
- results hook.

## Commit 4

`build completed run overview`

Changes:

- report summary;
- outcome stats;
- priority findings;
- lifecycle cleanup.

## Commit 5

`build findings and report views`

Changes:

- findings list;
- detail;
- report reading layout.

Only after those:

`add ambient markettwin motion system`

---

# 59. Exact UI Components to Add Initially

shadcn primitives:

```text
Button
Badge
Card
Tabs
Separator
Tooltip
DropdownMenu
Skeleton
Alert
Dialog
Sheet
ScrollArea
Progress
Table
Input
Textarea
Select
Sonner
Breadcrumb
Avatar
Command
```

MarketTwin components:

```text
AppSidebar
AppTopbar
PageHeading
RunLifecycle
RunOutcomeSummary
FindingSeverityBadge
FindingListItem
FindingEvidenceSummary
ReportSummary
Metric
EmptyState
ErrorState
AsyncContent
SignalBackground
```

---

# 60. Where the Supplied `aero-hero-3.tsx` Would Live

If copied exactly for experimentation:

```text
apps/web/src/components/ui/aero-hero-3.tsx
```

But the generic export name:

```tsx
export const Component = ...
```

should not survive production.

Rename it semantically if adapted.

Example:

```text
src/components/markettwin/signal-hero.tsx
```

Export:

```tsx
export function SignalHero() {}
```

The demo should live under:

```text
src/pages/system/DesignPlaygroundPage.tsx
```

or Storybook if Storybook is added later.

Do not import an experimental hero directly into core Run pages.

---

# 61. Assets

The instruction supplied suggests Unsplash.

For MarketTwin:

## Use Unsplash only if:

- a public landing page needs human/product imagery;
- licensing/remote asset policy is accepted.

## Prefer no stock photography inside the application

Authenticated MarketTwin should use:

- real evidence;
- UI-generated abstract visuals;
- icons;
- typography;
- product screenshots from the test itself.

This is more authentic.

---

# 62. Design Playground

Strong recommendation.

Create a temporary internal route:

```text
/dev/design
```

Only in local/development.

Show:

- tokens;
- buttons;
- badges;
- cards;
- statuses;
- persona cards;
- finding cards;
- evidence cards;
- shader background;
- typography;
- skeletons.

This speeds visual iteration dramatically.

It must not ship publicly in production.

---

# 63. Optional Storybook

Not required yet.

Add Storybook only if:

- component count increases substantially;
- multiple contributors need isolated component development;
- visual regression becomes difficult.

For current team size, a local Design Playground is simpler.

---

# 64. Dark Mode

The supplied theme supports `.dark`.

Recommendation:

Build tokens to support dark mode now.

Do **not** prioritize a user-facing dark-mode toggle before core UI completion.

Why:

- the current dark sidebar already provides visual richness;
- every evidence/report screen must be validated twice;
- it increases early design QA surface.

Implement theme switching after the main result experience stabilizes.

---

# 65. CSS Migration Strategy

Do not delete `styles.css` and rewrite everything in one shot.

Recommended:

## Stage 1
Add theme tokens + Tailwind/shadcn.

## Stage 2
Build new components using Tailwind.

## Stage 3
Migrate shell.

## Stage 4
Migrate run pages.

## Stage 5
Delete old selectors only when no longer referenced.

Use a search before deleting selectors.

This avoids visual regressions.

---

# 66. Current Custom Components

Keep temporarily:

- `BrandMark`
- `PageHeader`
- `StateViews`
- `StatusBadge`
- `LifecyclePanel`

Then decide one by one.

Likely:

### BrandMark
Keep.

### PageHeader
Refactor to Tailwind, retain concept.

### StateViews
Refactor to shadcn Alert/Skeleton/EmptyState.

### StatusBadge
Refactor around shadcn Badge.

### LifecyclePanel
Refactor into MarketTwin-specific `RunLifecycle`.

### Icon
Gradually replace with Lucide.

---

# 67. Brand Mark

Do not replace the MarketTwin brand mark with a generic Sparkles icon.

The brand should remain ownable.

Lucide should be used for interface actions, not the core MarketTwin logo.

---

# 68. Copy Style

MarketTwin copy should be:

- direct;
- specific;
- calm;
- evidence-oriented.

Use:

> 2 of 3 perspectives could not complete checkout.

Not:

> Our intelligent AI agents discovered an exciting opportunity to optimize your checkout experience!

Use:

> Evidence capture paused during human control.

Not:

> AI magic is paused while you take over.

This is a major anti-slop principle.

---

# 69. Persona Copy

Do not anthropomorphize excessively.

Good:

> This perspective prioritized price clarity and reversibility.

Bad:

> Sarah felt really anxious and confused.

Unless the persona definition explicitly includes such behavior and evidence supports it.

---

# 70. Trust Labels

Useful small labels:

- Observed
- Persona interpretation
- Deterministic finding
- Policy event
- Human action
- Evidence

These labels help the user understand provenance.

---

# 71. Evidence Provenance Pattern

Any finding detail should answer:

> Why should I believe this?

Show:

```text
Finding
  ↓
2 affected Journeys
  ↓
Execution steps
  ↓
2 screenshots
```

Use real links.

This should become a MarketTwin signature interaction.

---

# 72. “Explain This Finding” Future Feature

Later LLM-assisted UI could provide:

`Explain`

But its response must be visibly secondary to deterministic truth.

Possible UI:

```text
Evidence-backed finding
[core deterministic content]

AI synthesis
[optional explanation]
```

Do not merge them invisibly.

---

# 73. Run Completion Moment

When a run completes:

Avoid confetti.

Use a restrained state transition:

- lifecycle rail resolves;
- “Report ready” status;
- subtle highlight pulse once;
- CTA:
  - `Review Findings`
  - `Open Report`

Serious product research does not need celebration animation.

---

# 74. User Mental Model

A user should understand MarketTwin in five nouns:

```text
Study
→ Perspectives
→ Missions
→ Journeys
→ Findings
```

Evidence supports everything.

The navigation and visual hierarchy should reinforce this repeatedly.

---

# 75. User Experience Walkthrough

Think like a product manager using MarketTwin.

## Step 1: I open MarketTwin

I need to know:

- what workspace am I in?
- what products/apps are being tested?
- what happened recently?
- is anything actionable?

Do not start with product marketing.

## Step 2: I choose an application

I need:

- targets;
- authorization state;
- recent studies;
- quick create action.

## Step 3: I create a study

I need:

- one clear brief;
- target;
- confidence that MarketTwin handles the rest.

Do not make me configure 20 agent knobs.

## Step 4: Study runs

I need:

- what stage?
- is it stuck?
- which Journey is active?
- do you need me?

Do not show chain-of-thought.

## Step 5: Results

I need:

- what matters?
- how serious?
- how repeatable?

## Step 6: I inspect one issue

I need:

- who experienced it?
- what exactly happened?
- screenshot/evidence?
- recommendation?

## Step 7: I report to my team

I need:

- a readable summary;
- clear severity;
- evidence links;
- confidence that the result was not hallucinated.

This sequence should drive the UI.

---

# 76. What Would Make the UI Feel Bad

Avoid:

- every click opening a modal;
- enormous cards with little data;
- vague “AI is thinking” states;
- fake typing animations;
- hidden loading;
- status color without labels;
- error states presented as generic red banners;
- inaccessible custom selects;
- horizontal scroll for simple content;
- tiny fonts everywhere;
- endlessly disabled tabs;
- every page having a separate visual style;
- raw database IDs dominating normal screens;
- raw JSON as primary UX;
- shader animation under data tables;
- too many gradients;
- too much glass;
- stock-photo personas;
- emojis as main UI icons;
- unexplained technical terms;
- automatic destructive actions.

---

# 77. What Would Make Users Stay Engaged

Engagement should come from clarity and progress, not gamification.

Useful engagement:

- immediate study status;
- visible progressive discovery;
- meaningful timeline;
- clear “what changed”;
- finding count as work completes;
- easy movement finding → Journey → evidence;
- report that becomes progressively useful;
- saved filters/deep links later;
- keyboard navigation;
- responsive interactions;
- concise loading states.

---

# 78. Security UX

Targets are authorized resources.

Make authorization visible but not noisy.

Target header:

```text
Production
Authorized
example.com
```

Show expiry if applicable.

If authorization is missing:

- disable Start Study;
- clearly explain why;
- provide `Authorize Target`.

Never rely on a disabled button with no explanation.

---

# 79. S3/MinIO Evidence UX

Do not expose:

- bucket names;
- object keys;
- raw MinIO URLs

to normal users.

The frontend should eventually request an authenticated API URL.

Display:

- artifact type;
- associated step;
- created time;
- size if helpful.

Internal object storage details should stay implementation detail.

---

# 80. Frontend API Additions Needed Later

To finish all planned screens, backend will need read endpoints such as:

```text
GET /api/v1/test-runs/{id}/plan
GET /api/v1/test-runs/{id}/journeys
GET /api/v1/journeys/{id}
GET /api/v1/journeys/{id}/steps
GET /api/v1/test-runs/{id}/artifacts
GET /api/v1/artifacts/{id}
GET /api/v1/artifacts/{id}/content
GET /api/v1/test-runs/{id}/activity
```

Names can be adjusted during backend implementation.

The UI should not work around missing APIs by directly understanding database schema.

---

# 81. SSE / Live Run UI Later

When backend event wiring is ready:

```text
GET /api/v1/test-runs/{id}/events
```

or similar SSE stream.

UI behavior:

- connect once;
- reconcile with server state;
- reconnect with last event ID;
- do not assume events alone are authoritative;
- use final persisted API state as source of truth.

---

# 82. Design Tokens Beyond Color

Define tokens for:

## Spacing
Use Tailwind spacing scale.

## Page width
Recommended:

- standard: 1200–1280 px;
- report reading: 760–860 px;
- evidence inspector: wider.

## Motion
- fast: 120–160 ms
- normal: 180–240 ms
- spatial: 250–320 ms

## Z-index
Establish layers:

- content
- sticky header
- dropdown
- modal
- toast
- takeover/HITL

Do not scatter arbitrary `z-[9999]`.

---

# 83. Testing the User View

Before calling the UI “done,” manually perform these perspective reviews.

## Product manager

Can I identify the most important issue in 10 seconds?

## Designer

Can I open the exact evidence behind an issue?

## Engineer

Can I understand the execution path and reproduce it?

## Executive

Can I read the report without understanding MarketTwin internals?

## Security reviewer

Can I tell whether policy/human-auth boundaries were respected?

## Keyboard-only user

Can I complete the full workflow?

## Mobile user

Can I review urgent findings without desktop?

---

# 84. UI Quality Checklist

Before merging a UI phase:

### Visual
- clear hierarchy;
- consistent spacing;
- no accidental one-off colors;
- no duplicated visual patterns;
- no generic AI decoration.

### Interaction
- hover;
- active;
- focus-visible;
- disabled;
- loading;
- empty;
- error.

### Responsive
- desktop;
- laptop;
- tablet;
- mobile.

### Accessibility
- labels;
- headings;
- aria-live where needed;
- keyboard;
- contrast;
- target size;
- reduced motion.

### Data
- loading;
- missing values;
- long values;
- zero values;
- multiple findings;
- 50+ records.

### Performance
- no heavy rerender loop;
- images dimensioned;
- rich visual lazily loaded.

---

# 85. Recommended Dependencies

Immediate:

```json
{
  "lucide-react": "current compatible version",
  "clsx": "current compatible version",
  "tailwind-merge": "current compatible version",
  "class-variance-authority": "current compatible version",
  "tw-animate-css": "current compatible version"
}
```

Install shadcn components through the CLI so their primitive dependencies are explicit.

Later if justified:

```text
@tanstack/react-query
@tanstack/react-table
@tanstack/react-virtual
```

Do not install them before the UI actually needs them.

Avoid large general animation packages if CSS/shadcn motion is sufficient.

If the selected shader requires Motion/WebGL, scope the dependency to that one surface and lazy-load it.

---

# 86. Do We Need a UI Library Beyond shadcn?

No.

Recommended stack:

```text
React
TypeScript
Tailwind 4
shadcn/ui
Radix primitives via shadcn
Lucide
```

Do not add:

- Material UI;
- Chakra;
- Ant Design

on top of shadcn.

Multiple competing design systems create inconsistent behavior and bundle complexity.

---

# 87. Recommended First Real UI Step

## UI Step 1: Design System Foundation

Do only:

1. shadcn compatibility;
2. alias;
3. `cn`;
4. tokens;
5. Button;
6. Badge;
7. Card;
8. Skeleton;
9. Alert;
10. Tooltip;
11. Sheet;
12. Dialog;
13. Lucide;
14. keep all existing routes working.

Then stop and review the visible shell before moving to the next UI step.

This matches the project’s small-step development approach.

---

# 88. Final Product Visual Principle

Every important MarketTwin screen should pass this test:

> If the MarketTwin logo disappeared, would this still look specifically like a product for multi-perspective, evidence-backed product testing?

If the answer is no, the design is too generic.

The distinguishing visual patterns should be:

- perspective lanes;
- mission coverage;
- Journey traces;
- evidence links;
- finding reproduction;
- provenance;
- observation vs interpretation;
- live execution signal.

That is the design system.

Not a gradient.

---

# 89. Recommended V1 UI Roadmap

```text
UI-1  shadcn + tokens + Lucide
UI-2  shell redesign
UI-3  New Study redesign
UI-4  results API integration
UI-5  completed Run Overview
UI-6  Findings
UI-7  Report
UI-8  planning/persona/mission views
UI-9  Journey timeline
UI-10 Evidence inspector
UI-11 Live activity
UI-12 Human-assisted auth UI
UI-13 Accessibility/performance hardening
UI-14 Full frontend E2E
```

The first 7 are the highest priority now.

---

# 90. Definition of “UI V1 Done”

MarketTwin UI V1 should not be considered complete until a user can:

1. Sign in.
2. Enter a workspace.
3. Create an application.
4. Configure a target.
5. Authorize that target.
6. Create a study.
7. Start the study when execution dispatch is connected.
8. Watch lifecycle state.
9. Understand generated perspectives.
10. Understand missions.
11. Inspect each Journey.
12. See authoritative execution steps.
13. View screenshots/evidence.
14. Review prioritized findings.
15. See cross-perspective reproduction.
16. Read final report.
17. Perform required human login/MFA/CAPTCHA handoff.
18. Resume the same Journey.
19. Recover gracefully from loading/error/empty states.
20. Complete all major flows using keyboard.

---

# 91. Immediate Next Action

Do **not** start by building every page.

Start with:

## `UI Step 1 — shadcn-compatible design foundation`

Files likely touched:

```text
apps/web/package.json
apps/web/tsconfig.json
apps/web/vite.config.ts
apps/web/src/styles.css
apps/web/src/lib/utils.ts
apps/web/components.json
apps/web/src/components/ui/button.tsx
apps/web/src/components/ui/badge.tsx
apps/web/src/components/ui/card.tsx
apps/web/src/components/ui/skeleton.tsx
apps/web/src/components/ui/alert.tsx
apps/web/src/components/ui/tooltip.tsx
apps/web/src/components/ui/sheet.tsx
```

Validation:

```bash
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

Then visually review:

- Login.
- Sidebar.
- Overview.
- Applications.
- New Study.

Only after that move to the real results screens.

---

# 92. Source Notes

Research reviewed for this document:

- Existing MarketTwin repository, branch `refactor/python-browser-controller`.
- LinklyAI `best-skills`.
- Anthropic `frontend-design` skill description.
- Vercel Labs `vercel-react-best-practices`.
- Vercel Labs `web-design-guidelines`.
- Current Vercel Web Interface Guidelines.
- shadcn/ui Vite installation documentation.
- shadcn/ui Tailwind v4 documentation.
- Tailwind CSS v4 installation/upgrade documentation.
- W3C WCAG 2.2 guidance.
- 21st.dev Hero Animation and Shader component collections.
- The supplied Aero Hero and Tailwind theme code.

The 21st.dev reference was used as **visual inspiration**, not as a mandate to copy a marketing hero into the authenticated product.

---

# 93. Final Recommendation

Upgrade MarketTwin toward shadcn/Tailwind composition, but do not let shadcn determine the product’s personality.

Use shadcn for:

- accessible mechanics;
- predictable primitives;
- component consistency;
- keyboard behavior;
- composability.

Use MarketTwin-specific components for:

- the visual identity;
- Journey traces;
- persona representation;
- mission coverage;
- findings;
- evidence;
- lifecycle;
- human-control boundaries.

Use the animated shader reference as a carefully controlled moment of atmosphere.

The core product should earn user engagement through:

- clarity;
- speed;
- evidence;
- progressive disclosure;
- reproducibility;
- trust.

That combination is how MarketTwin can feel polished and modern without becoming “AI slop.”

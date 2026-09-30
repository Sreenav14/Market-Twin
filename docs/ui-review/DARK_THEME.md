# Dark theme review

## Research and decision

The request was to change MarketTwin to a dark theme. Dark is now the default
across sign-in and the workspace. This is a visual preference, not a claim that
dark mode improves every user's task performance. No study of MarketTwin users
was conducted, and this change does not add a theme switcher.

- [NN/g: Dark Mode—How Users Think About It and Issues to Avoid](https://www.nngroup.com/articles/dark-mode-users-issues/)
  reports mixed preferences in its survey of 115 mobile users: roughly equal
  groups used light, dark, or both. Lighting and individual needs matter; dark
  mode does not guarantee reduced eye strain. That argues for measured contrast
  and a consistent implementation rather than treating dark colors as a usability
  fix. System preference or a user-selected theme would be a separate enhancement.
- [Atlassian: Elevation](https://atlassian.design/foundations/elevation)
  explains that dark surfaces need tonal differences because shadows alone are
  difficult to perceive. MarketTwin uses a darker sidebar and page, slightly
  lighter panels, and lighter dialog surfaces. Hover surfaces change tone without
  adding motion or altering the layout.
- [Atlassian: Color](https://atlassian.design/foundations/color) and
  [GitHub Primer: Theming](https://primer.style/product/getting-started/react/theming/)
  use semantic theme roles. MarketTwin now keeps its color values in shared CSS
  tokens, including foreground/background pairs for status and primary actions.
  These are references for the approach; this palette is our application-specific
  design choice, not a copy of either product or evidence of a preferred hex value.
- [W3C: Text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
  requires at least 4.5:1 for normal text, while
  [W3C: Non-text contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)
  specifies 3:1 for necessary control/state indicators. Thin structural dividers
  need not meet the same threshold when they are not needed to identify a control.

## Changes and reasons

| File | Change | Reason |
| --- | --- | --- |
| `src/styles/tokens.css` | Charcoal page/sidebar/panels, soft light text, desaturated blue accent, semantic status pairs, overlay and scrim tokens; `color-scheme: dark` | Establish one coherent palette and let native form controls use the dark scheme. |
| `src/styles/legacy.css` | Replace hardcoded light backgrounds, foregrounds, status borders, form colors and state colors with tokens | Cover application, target and settings screens as well as the newer test screens; avoid white flashes on hover. |
| `src/styles/base.css` | Dark hover/status/icon/tooltip colors, readable placeholders and selection | Keep secondary interactions and every badge legible; use a separate dark foreground for light primary buttons. |
| `src/styles/workspace.css` | Token-based shell, table, composer, lifecycle and finding colors; lighter dialog surfaces and dark scrim | Preserve hierarchy and make dialogs distinguishable from the page. |
| `src/styles/signin.css` | Apply the same palette to both sign-in columns and supporting graphics | Avoid a bright login page before entering a dark workspace. |
| `src/components/ui/BrandMark.tsx` | Replace the white logo stroke with the primary-action foreground token | Visual inspection found the white line had weak contrast on the new light blue mark. |

Paths above are relative to `apps/web`. Layout, typography, button sizes, Kafka
badge placement, API behavior and run execution are unchanged by this theme work.
Screenshot evidence is displayed in its original colors; captured website images
are not inverted or recolored.

## Palette and contrast verification

| Role | Color |
| --- | --- |
| Page | `#14181e` |
| Sidebar | `#101419` |
| Panel | `#1c222a` |
| Muted surface | `#242c36` |
| Hover surface | `#2b3541` |
| Dialog surface | `#29333f` |
| Main / secondary / muted text | `#e6edf3` / `#bdc9d6` / `#9eafc0` |
| Primary / primary foreground | `#9bc7e8` / `#142331` |

WCAG relative-luminance calculations checked the text roles against all six main
surfaces, plus badge foreground/background pairs, primary button states and
control borders:

- Main text: minimum **10.53:1**; secondary text: **7.40:1**; muted text: **5.54:1**.
- Primary button text: **8.92:1**, rising to **10.59:1** on hover.
- Status text: success **7.50:1**, danger **7.13:1**, warning **7.67:1**, info **7.10:1**.
- Strong control borders: minimum **3.32:1** across those surfaces.

These calculations cover the defined opaque palette pairs. Browser accessibility
checks also inspect rendered content, where inheritance, transparency and layout
can change the result. Disabled controls are intentionally subdued. Status text
and icons remain in place so information does not depend on color alone.

## Validation

- Frontend TypeScript checking and the production build passed after the final
  logo adjustment. `git diff --check` passed.
- All **58 distinct existing browser checks** passed across desktop Chromium and
  mobile Chromium. The first full run passed 56; the two multi-page results tests
  exceeded 30 seconds under six concurrent browsers. A focused rerun using two
  workers and a 60-second limit passed all 10 selected checks, including those
  two and the screens whose logo screenshots needed refreshing.
- Existing browser checks include rendered WCAG A/AA accessibility audits, forms,
  completed results/detail/report, keyboard navigation, delete dialogs, empty
  states, expired authorization, polling, reduced motion and 320px reflow. They
  use intercepted API fixtures and do not start or delete real tests.
- Refreshed screenshots covered desktop/mobile sign-in,
  workspace, test creation, results, findings, report and narrow Start controls.
  Visual inspection covered sign-in and results before the logo correction,
  then the refreshed mobile sign-in, desktop composer and report afterward.
  Generated documentation screenshots were removed after review at the user's
  request; future captures use the ignored Playwright results directory.
- Palette calculations and automated audits do not establish every user's visual
  comfort. Firefox/Safari, screen-reader user studies and physical display/lighting
  comparisons were not performed. Captured evidence can still contain bright
  pages because it remains an accurate record of the tested site.

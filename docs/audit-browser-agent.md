# Public browser audit evidence — 2026-11-10

Status: both original browser failures resolved. Real desktop Chromium verification
passed **8/8**, exit 0, 74.37 seconds, no skipped/flaky/unexpected cases.

## Confirmed findings and repairs

1. **Medium: insufficient text contrast in the How-page illustration.**
   Existing real Chromium/axe evidence in
   `.local/audit-20261108/browser-public-final.json` identifies all three
   `THREAD & CO.` labels in `TriptychSignature.tsx` (lines 63, 139, 216).
   Foreground `--ink-faint` resolves to #79716B on #F5F4F2 paper: 4.35:1,
   below 4.5:1 for 11px text. Changed exactly those three labels to the existing
   `--ink-2` token (#57534E): calculated contrast 6.94:1. Existing How-page
   axe regression checks the rendered outcome; no assertion weakened.

2. **Test defect: stale navigation selectors cause the landing workflow timeout.**
   The recorded timeout is at `public-pages.spec.ts:27`, waiting for removed
   `Product navigation` -> `Sign in` link. Current `ConceptHeader` renders a
   `SIGN IN` button. The later home selector also expected a removed
   `MarketTwin home` link. Updated both to the current header buttons; retained
   page destination and heading assertions. No timeout increased.

## Additional product-copy discrepancy, no repair in this change

`PublicPages.tsx` HowPage still promises approval/freeze of a discovered checklist
(approximately lines 472–500 and 546–549), although the unified architecture
retires the contract approval flow. It also promises three personas contributing
to the verdict. `LoginPage.tsx` lines 178–188 repeats that older combined-verdict
model. This conflicts with the owner's separate Explore & Test and Persona Test
contract. Root informed; copy was not rewritten while architecture acceptance is
being assessed.

## Review coverage

Fully read: `TriptychSignature.tsx`, `ConceptHeader.tsx`, `ConceptFooter.tsx`,
`ContextTabs.tsx`, `AuthCallbackPage.tsx`, `public-pages.spec.ts`,
`playwright.config.ts`, `LoginPage.tsx`, `MegaMenu.tsx`.

Partially read: `PublicPages.tsx` (PublicLayout and full HowPage; earlier exports
not reviewed); `LandingPage.tsx` (entry/setup only);
`concept-tokens.css` (relevant color declarations only).

Concern only: `ContextTabs.tsx` creates Radix triggers without Content nodes;
example-page ARIA relationships need real browser verification before a repair.

## Commands and evidence

- Parsed the UTF-16 Playwright JSON with Python and inspected **all non-passed
  statuses**, including `timedOut`. Original summary: 6 expected, 2 unexpected.
- `curl.exe --silent --head --max-time 5 http://127.0.0.1:5173` -> exit 0, HTTP 200.
- Deterministic WCAG luminance calculation -> old 4.35:1, new 6.94:1. This is
  supporting calculation, not replacement for rendered axe verification.
- `git diff --check -- apps/web/e2e/public-pages.spec.ts
  apps/web/src/components/concept/TriptychSignature.tsx` -> exit 0.

All browser checks intercept API identity responses; they prove frontend behavior
and layout/accessibility, not backend authentication or provider integration.

## Fresh verification

Exact command:

```powershell
npm.cmd run test:e2e --workspace @markettwin/web -- --project=chromium public-pages.spec.ts route-protection.spec.ts smoke.spec.ts --workers=1 --reporter=json > .local/audit-20261108/browser-agent-final.json
```

Run started 2026-11-10 06:56:58 UTC. Existing Vite server reused at port 5173.
One heavy runner was used only after takeover released it; architecture notified
directly when this run finished. No application data was changed.

| Workflow | Expected/check | Result |
|---|---|---|
| Landing -> How -> login -> home | Current header controls reach correct URLs/headings | Pass |
| How evidence limits | Disclosure exposes missing-evidence explanation; axe + no overflow | Pass |
| Keyboard / URL input | Focus, invalid input, example activation, skip link and reduced motion | Pass |
| Login service outage | Mock 503 announced, focused, described to field; retry enabled; axe | Pass |
| Production callback | Honest unavailable-provider explanation and return link; axe | Pass |
| Responsive public pages | Landing/How/login/callback at 360/390/768/1024/1440, no overflow | Pass: 20 combinations |
| Route protection | Mock 401 redirects protected route to login | Pass |
| Login smoke | Email input, empty-submit disabled, serious/critical axe and overflow | Pass |

How screenshot visually inspected:
`apps/web/test-results/public-pages-How-explains--0c3f0--accessible-without-the-API-chromium/how.png`.
This inspection confirms the captured layout, not screen-reader or general device
acceptance. Console/network errors were not independently instrumented in these
existing tests; no claim of such coverage. Mobile Chromium project itself was not
run; narrow layouts were exercised by the explicit desktop viewport matrix.

Verified file SHA256 values:

- `TriptychSignature.tsx`: `3C94DA028FF92C6AAA32037526F2C0B79DA977DC74F6EE22E83775494A39EA76`
- `public-pages.spec.ts`: `7383A61C9225B19624E22A85D0EA92487D9AF8E3F07FD87D3C4FD7EBF1C728A9`

Only three production style lines and two test selectors were changed by this
agent. Pre-existing edits in public-pages.spec.ts remain intact. Root owns final
checkpoint and shared coverage inventory updates.

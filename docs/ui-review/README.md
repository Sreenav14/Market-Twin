# Local UI review

The screenshots in this directory show the implemented React application rendered by Playwright with explicit API test fixtures. They are visual review samples, not results from a live MarketTwin study. Production pages use the existing Control API.

## Review screens

- [Redesigned sign-in, desktop](signin-chromium.png)
- [Redesigned sign-in, mobile](signin-mobile-chromium.png)
- [Database deletion behavior and verification](DELETION.md)

- [Study overview, desktop](overview-chromium.png)
- [Findings, mobile](findings-mobile-chromium.png)
- [Report, desktop](report-chromium.png)
- [New study, mobile](new-study-mobile-chromium.png)
- [Workspace, desktop](workspace-chromium.png)

See [the UI audit](../UI_UX_AUDIT.md) for the architecture review, design decisions, source skills, and API boundaries.

## Run locally

From the repository root in PowerShell:

```powershell
npm.cmd run dev --workspace=@markettwin/web
```

Open http://localhost:5173. Normal use requires the Control API on port 8000 and your existing authentication/database setup. The UI does not substitute demo data when the API is unavailable.

## Reproduce checks

Final validation: TypeScript and production build passed; 9 frontend unit tests, 32 desktop/mobile browser tests, 44 backend tests, and one PostgreSQL deletion/cascade integration test passed. The tested screens had no automated WCAG A/AA violations or horizontal overflow. Desktop and mobile screenshots were also reviewed visually. These checks do not establish full accessibility conformance or replace testing with users.

```powershell
npm.cmd run typecheck --workspace=@markettwin/web
npm.cmd run test --workspace=@markettwin/web -- --maxWorkers=1
npm.cmd run build --workspace=@markettwin/web
```

With the development server running, in another terminal:

```powershell
npm.cmd run test:e2e --workspace=@markettwin/web -- --workers=1
```

The browser suite runs desktop Chromium and a Pixel 7 viewport. It checks navigation, study creation requests, findings/report workflows, waiting and error states, permissions, keyboard navigation, horizontal overflow, and automated accessibility. It also refreshes these screenshots. API responses are intercepted in tests; this does not verify a live backend execution or evaluation pipeline.

Detailed journey timelines, artifact downloads/inspection, live events, and human takeover still require the backend contracts identified in UI-7 through UI-10 of the implementation spec.

All changes are local. No deployment or GitHub push was performed.

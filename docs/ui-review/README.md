# Local UI review

This directory retains the written UI research, decisions and validation results.
Generated review screenshots were removed after visual verification at the user's
request. Future browser captures use Playwright's ignored `test-results` folder.
Production pages use the existing Control API.

## Review documents

- [Database deletion behavior and verification](DELETION.md)
- [Research and changelog](RESEARCH_AND_CHANGELOG.md)
- [Dark theme research and validation](DARK_THEME.md)

See [the UI audit](../UI_UX_AUDIT.md) for the architecture review, design decisions, source skills, and API boundaries.

## Run locally

From the repository root in PowerShell:

```powershell
npm.cmd run dev --workspace=@markettwin/web
```

Open http://localhost:5173. Normal use requires the Control API on port 8000 and your existing authentication/database setup. The UI does not substitute demo data when the API is unavailable.

## Reproduce checks

Run the checks after pulling the UI-hardening branch:

```powershell
npm.cmd run typecheck --workspace=@markettwin/web
npm.cmd run test --workspace=@markettwin/web -- --maxWorkers=1
npm.cmd run build --workspace=@markettwin/web
```

With the development server running, in another terminal:

```powershell
npm.cmd run test:e2e --workspace=@markettwin/web -- --workers=1
```

The browser suite runs desktop Chromium and a Pixel 7 viewport. It checks navigation, Test creation requests, findings/report workflows, waiting and error states, permissions, keyboard navigation, horizontal overflow, deletion rules, and automated accessibility. Screenshots are saved in ignored test output directories. API responses are intercepted in tests; this does not verify a live backend execution or evaluation pipeline.

Detailed journey timelines, artifact downloads/inspection, live events, and human takeover still require the backend contracts identified in the implementation spec.

The current UI-hardening work is on the `fix/ui-hardening-v1` branch. Test is the product term used in user-facing copy; `/runs` and `study_brief` remain internal V1 compatibility identifiers.

# MarketTwin Web

Enterprise React + TypeScript frontend for MarketTwin V1.

## Stack

- React
- TypeScript
- Vite
- React Router
- Tailwind CSS
- Vitest + React Testing Library
- Playwright + axe for E2E/accessibility

## Local development

From the repository root:

```powershell
npm install
npm run dev --workspace=@markettwin/web
```

The web app runs at `http://localhost:5173` and proxies `/api` requests to the Control API at `http://localhost:8000`.

## Quality commands

```powershell
npm run typecheck --workspace=@markettwin/web
npm run test --workspace=@markettwin/web
npm run build --workspace=@markettwin/web
npm run test:e2e --workspace=@markettwin/web
```

The frontend must not simulate backend capabilities. Planning, journey execution, human-assisted browser control, findings, evidence, report generation, lifecycle deletion, and member administration activate only when their corresponding backend contracts exist.

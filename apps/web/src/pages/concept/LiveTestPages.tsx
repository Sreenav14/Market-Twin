import { Link, useOutletContext } from "react-router-dom";
import type { RunContext } from "../../layouts/RunLayout";
import { RunActivityPage } from "../runs/RunActivityPage";
import { RunReportPage } from "../runs/RunReportPage";

// Keep the evidence-aware renderers and permission checks for every execution mode.
export function LiveTestPage({ view }: { view: "watch" | "results" }) {
  const { run } = useOutletContext<RunContext>();
  return <div className="concept-live-test">
    <nav className="concept-live-test-tabs" aria-label="In-test views">
      <Link to={`/runs/${run.id}/results`} aria-current={view === "results" ? "page" : undefined}>Test results</Link>
      <Link to={`/runs/${run.id}/watch`} aria-current={view === "watch" ? "page" : undefined}>Watch live</Link>
    </nav>
    {view === "watch" ? <RunActivityPage /> : <RunReportPage />}
  </div>;
}

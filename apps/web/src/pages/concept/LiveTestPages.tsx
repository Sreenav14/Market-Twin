import { RunActivityPage } from "../runs/RunActivityPage";
import { RunReportPage } from "../runs/RunReportPage";

// Keep the evidence-aware renderers and permission checks for every execution mode.
// The in-test tab strip is owned by RunLayout; this wrapper only picks the renderer
// for the watch/results routes so the two never stack duplicate tab bars.
export function LiveTestPage({ view }: { view: "watch" | "results" }) {
  return <div className="concept-live-test">
    {view === "watch" ? <RunActivityPage /> : <RunReportPage />}
  </div>;
}

import type { ReactNode } from "react";
import { useOutletContext } from "react-router-dom";
import { Clock3, FileSearch } from "lucide-react";
import type { RunContext } from "../../layouts/RunLayout";
import { ErrorPanel, LoadingPanel } from "../ui/StateViews";
import { Button } from "../ui/button";

export function ResultsBoundary({ children }: { children: ReactNode }) {
  const { run, results, refresh } = useOutletContext<RunContext>();
  if (results.status === "loading") return <LoadingPanel label="Loading evaluation" />;
  if (results.status === "error") return <ErrorPanel message={results.error} action={<Button variant="secondary" onClick={refresh}>Try again</Button>} />;
  if (results.status === "waiting") {
    const completed = run.status === "completed";
    const stopped = ["failed", "cancelled", "timed_out", "policy_blocked"].includes(run.status);
    return <section className="waiting-state"><span className="state-icon">{completed ? <FileSearch size={28} aria-hidden="true" /> : <Clock3 size={28} aria-hidden="true" />}</span><h2>{completed ? "Evaluation is not available yet" : stopped ? "This test ended without a report" : "Results will appear here"}</h2><p>{completed ? "Execution is complete. This view will update when the evaluation becomes available." : stopped ? "Review the test status and target configuration before starting another test." : "The test is still in progress. Findings and the final report become available after completion."}</p><Button variant="secondary" onClick={refresh}>Check again</Button></section>;
  }
  return <>{children}</>;
}

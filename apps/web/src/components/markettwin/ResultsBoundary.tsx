import type { ReactNode } from "react";
import { useOutletContext } from "react-router-dom";
import { Clock3, FileSearch } from "lucide-react";
import type { RunContext } from "../../layouts/RunLayout";
import { ErrorPanel, LoadingPanel } from "../ui/StateViews";
import { Button } from "../ui/button";

export function ResultsBoundary({ children }: { children: ReactNode }) {
  const { run, results, refresh } = useOutletContext<RunContext>();
  const featureRun = run.configuration_snapshot.execution_mode === "deep_feature_v1";
  if (results.status === "loading")
    return <LoadingPanel label="Loading evaluation" />;
  if (results.status === "error")
    return (
      <ErrorPanel
        message={results.error}
        action={
          <Button variant="secondary" onClick={refresh}>
            Try again
          </Button>
        }
      />
    );
  if (results.status === "waiting") {
    const completed = run.status === "completed";
    const stopped = [
      "failed",
      "cancelled",
      "timed_out",
      "policy_blocked",
    ].includes(run.status);
    return (
      <section className="waiting-state">
        <span className="state-icon">
          {completed ? (
            <FileSearch size={28} aria-hidden="true" />
          ) : (
            <Clock3 size={28} aria-hidden="true" />
          )}
        </span>
        <h2>
          {completed
            ? "Preparing evaluation"
            : stopped
              ? "This test ended without a report"
              : "Results will appear here"}
        </h2>
        <p>
          {completed
            ? "Browser execution is complete. Evaluation is still pending, so product findings are not ready. This page checks automatically. If it continues waiting, ask your workspace operator to check the evaluation worker; its status is also shown in the test flow."
            : stopped
              ? "Review the test status and target configuration before starting another test."
              : run.status === "awaiting_human"
                ? "This test is paused for an authorized human action. Open Human Assistance to review the request; results remain unverified."
              : run.status === "draft"
                ? featureRun
                  ? "Start this draft to plan and execute feature cases. Evaluation follows recorded browser execution."
                  : "Start this draft to create agents and execute its journeys. Evaluation follows execution."
                : run.status === "queued"
                  ? "This test is waiting for an execution worker. Evaluation starts after its journeys finish."
                  : featureRun
                    ? "Feature-case planning or browser execution is in progress. Evaluation follows execution; findings and the final report are not ready yet."
                    : "Agents are still planning or executing journeys. Evaluation follows execution; findings and the final report are not ready yet."}
        </p>
        <Button variant="secondary" onClick={refresh}>
          Check again
        </Button>
      </section>
    );
  }
  return <>{children}</>;
}

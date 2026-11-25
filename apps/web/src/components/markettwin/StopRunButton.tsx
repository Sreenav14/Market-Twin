import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type TestRun } from "../../lib/api";
import { Button } from "../ui/button";

const STOPPABLE_STATUSES = new Set([
  "planning",
  "queued",
  "running",
  "awaiting_human",
]);

/**
 * Owner stop for a live run. The button records a durable stop
 * request (ctl writes an `owner_stop` flag on the run); the engine
 * honours it at the next item boundary — the current check
 * finishes, the rest close as not checked, and the run closes
 * cancelled. Inline confirm only: no modal machinery.
 */
export function StopRunButton({ run }: { run: TestRun }) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [requested, setRequested] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const stop = useMutation({
    mutationFn: () => api.stopRun(run.id),
    onSuccess: () => {
      setRequested(true);
      setConfirming(false);
      void queryClient.invalidateQueries({ queryKey: ["run"] });
    },
    onError: () =>
      setError("The stop request could not be recorded. Try again."),
  });
  if (!STOPPABLE_STATUSES.has(run.status)) return null;
  const snapshotFlag = run.configuration_snapshot?.["owner_stop"];
  if (requested || (typeof snapshotFlag === "object" && snapshotFlag !== null)) {
    return (
      <p className="run-stop-requested" role="status">
        Stop requested — the run is closing down: the current check
        finishes and the rest close as not checked.
      </p>
    );
  }
  if (!confirming) {
    return (
      <Button
        variant="destructive"
        size="sm"
        onClick={() => setConfirming(true)}
      >
        Stop run
      </Button>
    );
  }
  return (
    <div
      className="run-stop-confirm"
      role="group"
      aria-label="Confirm stopping this run"
    >
      <p>
        Stop this run? The current check finishes; everything not yet
        checked closes as not checked.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      <Button
        variant="destructive"
        size="sm"
        disabled={stop.isPending}
        onClick={() => stop.mutate()}
      >
        Stop run
      </Button>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setConfirming(false)}
      >
        Keep running
      </Button>
    </div>
  );
}

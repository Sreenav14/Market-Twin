import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { Button } from "../ui/button";
import { Tooltip } from "../ui/tooltip";
import { Dialog } from "../ui/Dialog";
import { InlineAlert, useToast } from "../ui/Feedback";
import { api } from "../../lib/api";

export function DeleteAction({
  kind,
  id,
  name,
  onDeleted,
  disabled = false,
  workspaceId,
}: {
  id: string;
  name: string;
  onDeleted: () => void;
  disabled?: boolean;
} & ({ kind: "knowledge"; workspaceId: string } | { kind: "test" | "target" | "application"; workspaceId?: never })) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef(false);
  const cancel = useRef<HTMLButtonElement>(null);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  async function remove() {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(null);
    try {
      if (kind === "knowledge") {
        await api.deleteIngestion(workspaceId, id);
      } else await {
        test: api.deleteRun,
        target: api.deleteTarget,
        application: api.deleteApplication,
      }[kind](id);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Unable to delete. Please try again.",
      );
      pending.current = false;
      setBusy(false);
      return;
    }

    if (kind === "test") {
      queryClient.removeQueries({
        predicate: (query) =>
          ["run", "results"].includes(String(query.queryKey[0])) &&
          query.queryKey.includes(id),
      });
    }
    if (kind === "knowledge") {
      queryClient.removeQueries({
        predicate: (query) =>
          ["knowledge-review", "knowledge-source"].includes(String(query.queryKey[0])) &&
          query.queryKey.includes(workspaceId) && query.queryKey.includes(id),
      });
      await queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] === "ingestion" && query.queryKey.includes(workspaceId),
      });
    }
    await queryClient.invalidateQueries({ queryKey: ["workspace-tests"] });
    if (kind === "target")
      await queryClient.invalidateQueries({ queryKey: ["test-targets"] });

    setOpen(false);
    setBusy(false);
    pending.current = false;
    toast({ title: `${kind[0].toUpperCase()}${kind.slice(1)} deleted`, body: name });
    onDeleted();
  }

  const trigger = (
    <Button
      variant="ghost"
      className="delete-trigger"
      disabled={disabled}
      aria-label={`Delete ${kind}: ${name}`}
    >
      <Trash2 size={16} aria-hidden="true" />
      <span>Delete</span>
    </Button>
  );

  if (disabled) {
    const message =
      kind === "test"
        ? "Queued and in-progress tests cannot be deleted. Wait for the test to finish."
        : `This ${kind} cannot be deleted while it still has dependent records.`;
    return (
      <Tooltip text={message}>
        <span className="disabled-control" tabIndex={0} aria-label={message}>
          {trigger}
        </span>
      </Tooltip>
    );
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!pending.current) {
          setOpen(value);
          setError(null);
        }
      }}
      trigger={trigger}
      title={`Delete ${kind}: ${name}?`}
      size="sm"
      alert
      busy={busy}
      initialFocusRef={cancel}
      description={
        kind === "knowledge"
          ? "This removes the set from your knowledge library and future test selection. Existing tests keep their saved knowledge and source history."
          : kind === "test"
            ? "This permanently removes the test and its results and evidence records. This cannot be undone."
            : `This permanently removes the ${kind}. ${kind === "target" ? "Delete its tests first." : "Delete its tests and targets first."} This cannot be undone.`
      }
      footer={
        <>
          <button
            ref={cancel}
            type="button"
            className="secondary-button"
            disabled={busy}
            onClick={() => setOpen(false)}
          >
            Keep {kind}
          </button>
          <Button variant="destructive" onClick={() => void remove()} disabled={busy}>
            {busy ? "Deleting\u2026" : `Delete ${kind}`}
          </Button>
        </>
      }
    >
      {error ? (
        <InlineAlert severity="error" title="Could not delete" role="alert">
          {error}
        </InlineAlert>
      ) : null}
    </Dialog>
  );
}

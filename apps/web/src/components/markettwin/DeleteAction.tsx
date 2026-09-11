import * as Dialog from "@radix-ui/react-dialog";
import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { Button } from "../ui/button";
import { api } from "../../lib/api";

export function DeleteAction({ kind, id, name, onDeleted, disabled = false }: {
  kind: "test" | "target" | "application"; id: string; name: string;
  onDeleted: () => void; disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef(false);
  const cancel = useRef<HTMLButtonElement>(null);
  const queryClient = useQueryClient();
  async function remove() {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(null);
    try {
      await ({ test: api.deleteRun, target: api.deleteTarget, application: api.deleteApplication })[kind](id);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Unable to delete. Please try again.");
      pending.current = false; setBusy(false); return;
    }
    await queryClient.cancelQueries();
    if (kind === "test") {
      queryClient.removeQueries({ predicate: query => ["run", "results"].includes(String(query.queryKey[0])) && query.queryKey.includes(id) });
    }
    void queryClient.invalidateQueries();
    setOpen(false); setBusy(false); pending.current = false; onDeleted();
  }
  return <Dialog.Root open={open} onOpenChange={value => { if (!pending.current) { setOpen(value); setError(null); } }}>
    <Dialog.Trigger asChild><Button variant="ghost" className="delete-trigger" disabled={disabled} aria-label={`Delete ${kind}: ${name}`} title={disabled ? "Wait until this test finishes before deleting it." : `Delete ${kind}`}><Trash2 size={16} aria-hidden="true" /><span>Delete</span></Button></Dialog.Trigger>
    <Dialog.Portal><Dialog.Overlay className="command-overlay" /><Dialog.Content className="delete-dialog" onOpenAutoFocus={event => { event.preventDefault(); cancel.current?.focus(); }}>
      <Dialog.Title>Delete {kind}?</Dialog.Title>
      <Dialog.Description className="delete-description">{kind === "test" ? "This permanently removes the test and its results from MarketTwin. Stored artifact files are retained separately." : `This permanently removes the ${kind}. ${kind === "target" ? "Delete its tests first." : "Delete its tests and targets first."}`} This cannot be undone.</Dialog.Description>
      <p className="delete-item-name">{name}</p>
      {error ? <p role="alert" className="form-error">{error}</p> : null}
      <div className="delete-dialog-actions"><Dialog.Close asChild><button ref={cancel} type="button" className="secondary-button" disabled={busy}>Cancel</button></Dialog.Close><Button variant="destructive" onClick={() => void remove()} disabled={busy}>{busy ? "Deleting…" : `Delete ${kind}`}</Button></div>
    </Dialog.Content></Dialog.Portal>
  </Dialog.Root>;
}

import { useRef, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../components/ui/button";
import { Dialog, DiscardChangesDialog } from "../../components/ui/Dialog";
import { FieldError, RequiredMark } from "../../components/ui/Field";
import { InlineAlert, useToast } from "../../components/ui/Feedback";
import { api, type IngestionEntry } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { type AppShellContext } from "../../layouts/AppShell";

type Props = { entry: IngestionEntry; onSaved: (entry: IngestionEntry) => void };

export function RenameKnowledge({ entry, onSaved }: Props) {
  const { workspace } = useOutletContext<AppShellContext>();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(entry.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nameSubmitted, setNameSubmitted] = useState(false);
  const nameError = nameSubmitted && !name.trim() ? "Enter a knowledge set name." : null;
  async function save() {
    setNameSubmitted(true);
    if (!name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api.renameIngestion(workspace.id, entry.id, name.trim());
      onSaved(saved);
      toast({ title: "Name saved", body: saved.name });
      setOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not rename knowledge.");
    } finally { setBusy(false); }
  }
  const { toast } = useToast();
  const dirty = name.trim() !== entry.name && name.trim().length > 0;
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const firstField = useRef<HTMLInputElement>(null);
  return <>
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!busy) { setOpen(value); if (!value) { setName(entry.name); setError(null); } }
      }}
      trigger={<Button variant="secondary">Rename</Button>}
      title="Rename knowledge"
      description="Give this set a name that helps you find it."
      size="md"
      form
      dirty={dirty}
      onDirtyAttempt={() => setConfirmDiscard(true)}
      busy={busy}
      initialFocusRef={firstField}
      footer={
        <>
          <Button type="button" variant="secondary" disabled={busy} onClick={() => {
            if (dirty) setConfirmDiscard(true);
            else { setOpen(false); setName(entry.name); setError(null); }
          }}>Cancel</Button>
          <Button type="submit" form="rename-knowledge-form" disabled={busy}>{busy ? "Saving\u2026" : "Save name"}</Button>
        </>
      }
    >
      <form id="rename-knowledge-form" className="form-grid" onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <label className="field-label" htmlFor="rename-knowledge">Knowledge set name <RequiredMark required /></label>
        <input ref={firstField} id="rename-knowledge" className="text-input" value={name} onChange={(event) => setName(event.target.value)} required maxLength={200} disabled={busy} aria-invalid={nameError ? true : undefined} aria-describedby={nameError ? "rename-knowledge-error" : undefined} />
        {nameError ? <FieldError id="rename-knowledge-error">{nameError}</FieldError> : null}
                {error ? <InlineAlert severity="error" title="Could not save" role="alert">{error}</InlineAlert> : null}
      </form>
    </Dialog>
    <DiscardChangesDialog
      open={confirmDiscard}
      onKeep={() => setConfirmDiscard(false)}
      onDiscard={() => { setConfirmDiscard(false); setOpen(false); setName(entry.name); setError(null); }}
    />
  </>;
}

export function KnowledgeApplications({ entry, onSaved }: Props) {
  const { workspace, user } = useOutletContext<AppShellContext>();
  const [selected, setSelected] = useState(entry.application_ids ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();
  const canWrite = canWriteWorkspace(workspace.role);
  const applications = useQuery({ queryKey: ["applications", user.id, workspace.id], queryFn: () => api.listApplications(workspace.id) });
  const changed = [...selected].sort().join() !== [...(entry.application_ids ?? [])].sort().join();
  async function save() {
    setBusy(true);
    setError(null);
    try {
      onSaved(await api.attachIngestion(workspace.id, entry.id, selected));
      toast({ title: "Applications saved", body: "This knowledge is attached to the selected apps." });
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not update applications."); }
    finally { setBusy(false); }
  }
  return <section className="panel section-block">
    <h2>Your apps</h2>
    <p className="muted">Attach this approved knowledge to the applications that should use it. Select it when creating a test.</p>
    {applications.isPending ? <p role="status">Loading applications…</p> : applications.isError ? <InlineAlert severity="error" title="Could not load applications" role="alert" action={<Button variant="ghost" size="sm" onClick={() => void applications.refetch()}>Try again</Button>} /> : applications.data.length ? <>
      <fieldset className="knowledge-choices" disabled={busy || !canWrite}>
        <legend className="visually-hidden">Attach knowledge to applications</legend>
        {applications.data.map((application) => <div className="knowledge-choice" key={application.id}>
          <label><input type="checkbox" className="mt-checkbox" checked={selected.includes(application.id)} onChange={(event) => setSelected((previous) => event.target.checked ? [...previous, application.id] : previous.filter((id) => id !== application.id))} /><span>{application.name}</span></label>
          {canWrite && application.status === "active" && entry.application_ids?.includes(application.id) ? <Link className="text-link" to={`/applications/${application.id}/runs/new`}>Start a test<span className="visually-hidden"> for {application.name}</span></Link> : null}
        </div>)}
      </fieldset>
              {error ? <InlineAlert severity="error" title="Could not save" role="alert">{error}</InlineAlert> : null}
      {canWrite ? <div className="form-actions"><Button variant="secondary" disabled={busy || !changed} onClick={() => void save()}>{busy ? "Saving…" : "Save applications"}</Button></div> : null}
    </> : <p>No apps yet.{canWrite ? <> <Link className="text-link" to="/applications/new">Add an app</Link> to attach this knowledge.</> : null}</p>}
  </section>;
}

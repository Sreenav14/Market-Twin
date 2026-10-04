import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../components/ui/button";
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
  async function save() {
    if (!name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      onSaved(await api.renameIngestion(workspace.id, entry.id, name.trim()));
      setOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not rename knowledge.");
    } finally { setBusy(false); }
  }
  return <Dialog.Root open={open} onOpenChange={(value) => {
    if (!busy) { setOpen(value); setName(entry.name); setError(null); }
  }}>
    <Dialog.Trigger asChild><Button variant="secondary">Rename</Button></Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Overlay className="dialog-overlay" />
      <Dialog.Content className="delete-dialog">
        <Dialog.Title>Rename knowledge</Dialog.Title>
        <Dialog.Description className="delete-description">Give this set a name that helps you find it.</Dialog.Description>
        <form className="form-grid" onSubmit={(event) => { event.preventDefault(); void save(); }}>
          <label className="field-label" htmlFor="rename-knowledge">Knowledge set name</label>
          <input id="rename-knowledge" className="text-input" value={name} onChange={(event) => setName(event.target.value)} required maxLength={200} disabled={busy} />
          {error ? <p role="alert" className="form-error">{error}</p> : null}
          <div className="delete-dialog-actions">
            <Dialog.Close asChild><Button type="button" variant="secondary" disabled={busy}>Cancel</Button></Dialog.Close>
            <Button type="submit" disabled={busy || !name.trim()}>{busy ? "Saving…" : "Save name"}</Button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}

export function KnowledgeApplications({ entry, onSaved }: Props) {
  const { workspace, user } = useOutletContext<AppShellContext>();
  const [selected, setSelected] = useState(entry.application_ids ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canWrite = canWriteWorkspace(workspace.role);
  const applications = useQuery({ queryKey: ["applications", user.id, workspace.id], queryFn: () => api.listApplications(workspace.id) });
  const changed = [...selected].sort().join() !== [...(entry.application_ids ?? [])].sort().join();
  async function save() {
    setBusy(true);
    setError(null);
    try { onSaved(await api.attachIngestion(workspace.id, entry.id, selected)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not update applications."); }
    finally { setBusy(false); }
  }
  return <section className="panel section-block">
    <h2>Applications</h2>
    <p className="muted">Attach this approved knowledge to the applications that should use it. Select it when creating a test.</p>
    {applications.isPending ? <p role="status">Loading applications…</p> : applications.isError ? <p role="alert" className="form-error">Could not load applications. <Button variant="ghost" size="sm" onClick={() => void applications.refetch()}>Try again</Button></p> : applications.data.length ? <>
      <fieldset className="knowledge-choices" disabled={busy || !canWrite}>
        <legend className="visually-hidden">Attach knowledge to applications</legend>
        {applications.data.map((application) => <div className="knowledge-choice" key={application.id}>
          <label><input type="checkbox" checked={selected.includes(application.id)} onChange={(event) => setSelected((previous) => event.target.checked ? [...previous, application.id] : previous.filter((id) => id !== application.id))} /><span>{application.name}</span></label>
          {entry.application_ids?.includes(application.id) ? <Link className="text-link" to={`/applications/${application.id}/runs/new`}>Create test<span className="visually-hidden"> for {application.name}</span></Link> : null}
        </div>)}
      </fieldset>
      {error ? <p role="alert" className="form-error">{error}</p> : null}
      {canWrite ? <div className="form-actions"><Button variant="secondary" disabled={busy || !changed} onClick={() => void save()}>{busy ? "Saving…" : "Save applications"}</Button></div> : null}
    </> : <p>No applications yet. <Link className="text-link" to="/applications/new">Add an application</Link> to attach this knowledge.</p>}
  </section>;
}

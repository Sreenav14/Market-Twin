import { FormEvent, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { PageHeader } from "../../components/ui/PageHeader";
import { Spinner } from "../../components/ui/StateViews";
import { api } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { AppShellContext } from "../../layouts/AppShell";

export function NewApplicationPage() {
  const navigate = useNavigate();
  const { workspace } = useOutletContext<AppShellContext>();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canWriteWorkspace(workspace.role)) {
    return <><PageHeader eyebrow="Applications" title="Add application" /><div className="error-panel" role="alert"><div><strong>Read-only workspace</strong><span>Your workspace role cannot create applications.</span></div></div></>;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const application = await api.createApplication(workspace.id, name.trim(), description.trim());
      navigate(`/applications/${application.id}`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Could not create application.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="Applications" title="Add application" description="Create a product container. Targets and studies remain scoped to this application." />
      <form className="panel form-grid form-card" onSubmit={submit}>
        <label className="field-label" htmlFor="app-name">Name</label>
        <input id="app-name" className="text-input" value={name} onChange={(event) => { setName(event.target.value); setError(null); }} placeholder="Acme Checkout" required maxLength={200} autoFocus />
        <label className="field-label" htmlFor="app-description">Description <span>Optional</span></label>
        <textarea id="app-description" className="text-area" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What product or product area will your team evaluate?" rows={4} />
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <div className="form-actions"><button className="secondary-button" type="button" onClick={() => navigate(-1)}>Cancel</button><button className="primary-button" type="submit" disabled={busy || !name.trim()}>{busy ? <><Spinner /> Creating</> : "Create application"}</button></div>
      </form>
    </>
  );
}

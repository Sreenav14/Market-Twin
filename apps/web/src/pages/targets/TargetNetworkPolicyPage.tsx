import { FormEvent, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import { PageHeader } from "../../components/ui/PageHeader";
import { ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { api } from "../../lib/api";
import { canAuthorizeTarget } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

function originLabel(origin: { scheme: string; hostname: string; port: number | null }) {
  const host = origin.hostname.includes(":") ? `[${origin.hostname}]` : origin.hostname;
  return `${origin.scheme}://${host}${origin.port ? `:${origin.port}` : ""}`;
}

export function TargetNetworkPolicyPage() {
  const { targetId = "" } = useParams();
  const { workspace } = useOutletContext<AppShellContext>();
  const [revision, setRevision] = useState(0);
  const state = useAsync(async () => ({
    target: await api.getTarget(targetId),
    revisions: await api.listScopeRevisions(targetId),
  }), [targetId, revision]);
  const [name, setName] = useState("");
  const [origins, setOrigins] = useState("");
  const [basis, setBasis] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (state.status === "loading") return <LoadingPanel label="Loading execution scopes" />;
  if (state.status === "error") return <ErrorPanel message={state.error} />;
  const { target, revisions } = state.data;
  const mayRequest = canAuthorizeTarget(workspace.role);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      await api.requestScopeRevision(targetId, {
        name: name.trim(), origins: origins.split(/\r?\n/).map((value) => value.trim()).filter(Boolean),
        request_basis: basis.trim(),
      });
      setRevision((value) => value + 1);
      setName(""); setOrigins(""); setBasis(""); setConfirmed(false);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not request scope review.");
    } finally { setBusy(false); }
  }
  return <>
    <PageHeader eyebrow="Target network policy" title="Execution scopes"
      description="Additional destinations require an exact scope and separate owner or admin approval." />
    <section className="panel">
      <h2>Current scope: {target.name}</h2>
      <ul>{target.allowed_origins.map((origin) => <li key={originLabel(origin)}>
        <code>{originLabel(origin)}</code>{origin.include_subdomains ? " (legacy subdomain permission)" : " (exact origin)"}
      </li>)}</ul>
      <p>Existing tests keep their frozen permissions. A new scope creates a separate target; it cannot execute until explicitly authorized. Select that newly approved target when creating a new test.</p>
      {target.scope_parent_id ? <Link to={`/targets/${target.scope_parent_id}/network`}>Original execution scope</Link> : null}
    </section>
    <section className="panel">
      <h2>Request a new execution scope</h2>
      {mayRequest ? <form className="form-grid" onSubmit={submit}>
        <label className="field-label" htmlFor="scope-name">New target name</label>
        <input className="text-input" id="scope-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={200} />
        <label className="field-label" htmlFor="scope-origins">Complete exact-origin scope, one per line</label>
        <textarea className="text-area" id="scope-origins" value={origins} onChange={(event) => setOrigins(event.target.value)} rows={5} required placeholder={target.allowed_origins.map(originLabel).join("\n")} />
        <p>Include the base origin and each approved application or SSO origin. Paths, wildcards and automatic subdomain trust are not supported.</p>
        <label className="field-label" htmlFor="scope-basis">Reason for this requested scope</label>
        <textarea className="text-area" id="scope-basis" value={basis} onChange={(event) => setBasis(event.target.value)} rows={3} minLength={10} maxLength={2000} required />
        <label className="confirmation-row"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I understand this creates a pending target and does not authorize execution.</label>
        {error ? <p role="alert" className="form-error">{error}</p> : null}
        <button className="primary-button align-start" disabled={busy || !confirmed || basis.trim().length < 10 || !name.trim()}>{busy ? "Creating scope request" : "Create pending scope"}</button>
      </form> : <p>Only workspace owners and admins can request or authorize new execution scopes.</p>}
    </section>
    <section className="panel"><h2>Requested scope revisions</h2>
      {!revisions.length ? <p>No scope revisions requested.</p> : <ul>{revisions.map((item) => <li key={item.id}>
        <strong>{item.name}</strong><ul>{item.allowed_origins.map((origin) => <li key={originLabel(origin)}><code>{originLabel(origin)}</code></li>)}</ul>
        <Link to={`/targets/${item.id}/authorization`}>Review authorization status and scope</Link>
      </li>)}</ul>}
    </section>
  </>;
}

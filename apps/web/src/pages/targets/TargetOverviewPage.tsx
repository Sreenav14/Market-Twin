import { Link, useOutletContext, useParams } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";
import { LifecyclePanel } from "../../components/ui/LifecyclePanel";
import { PageHeader } from "../../components/ui/PageHeader";
import { ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { ApiError, TargetAuthorization, api } from "../../lib/api";
import { canManageLifecycle, canWriteWorkspace } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function TargetOverviewPage() {
  const { targetId = "" } = useParams(); const { workspace } = useOutletContext<AppShellContext>();
  const targetState = useAsync(() => api.getTarget(targetId), [targetId]);
  const authorizationState = useAsync<TargetAuthorization | null>(async () => { try { return await api.getAuthorization(targetId); } catch (error) { if (error instanceof ApiError && error.status === 404) return null; throw error; } }, [targetId]);
  if (targetState.status === "loading" || authorizationState.status === "loading") return <LoadingPanel label="Loading target" />;
  if (targetState.status === "error") return <ErrorPanel message={targetState.error} />;
  if (authorizationState.status === "error") return <ErrorPanel message={authorizationState.error} />;
  const target = targetState.data; const authorization = authorizationState.data; const authorized = authorization?.status === "authorized"; const canWrite = canWriteWorkspace(workspace.role) && target.status === "active";
  return <><PageHeader eyebrow="Target" title={target.name} description={target.base_url} action={authorized && canWrite ? <Link className="primary-button" to={`/applications/${target.application_id}/runs/new`}><Icon name="plus" size={16} /> New study</Link> : <Link className="primary-button" to={`/targets/${target.id}/authorization`}><Icon name="shield" size={16} /> Authorization</Link>} /><div className="detail-grid"><section className="panel"><div className="section-heading compact-heading"><div><p className="eyebrow">Configuration</p><h2>Target details</h2></div><StatusBadge status={target.status} /></div><dl className="definition-list"><div><dt>Environment</dt><dd>{target.environment}</dd></div><div><dt>Authentication</dt><dd>{target.requires_auth ? "Protected" : "Public"}</dd></div><div><dt>Authorization</dt><dd><StatusBadge status={authorization?.status ?? "not authorized"} /></dd></div><div><dt>Base URL</dt><dd className="monospace">{target.base_url}</dd></div></dl></section><section className="panel"><div className="section-heading compact-heading"><div><p className="eyebrow">Network</p><h2>Allowed origins</h2></div></div><div className="origin-list">{target.allowed_origins.map((origin) => <div key={`${origin.scheme}-${origin.hostname}-${origin.port ?? "default"}`}><code>{origin.scheme}://{origin.hostname}{origin.port ? `:${origin.port}` : ""}</code><span>{origin.include_subdomains ? "Includes subdomains" : "Exact host"}</span></div>)}</div><p className="panel-note">Additional origin management needs a dedicated Control API. The UI will not offer an unsafe “allow all” shortcut.</p></section></div>{canManageLifecycle(workspace.role) ? <LifecyclePanel entityType="target" entityName={target.name} /> : null}</>;
}

import { useOutletContext } from "react-router-dom";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { roleLabel } from "../../lib/permissions";
import { AppShellContext } from "../../layouts/AppShell";
export function WorkspaceSettingsPage() { const { workspace }=useOutletContext<AppShellContext>(); return <section className="panel settings-panel"><div className="section-heading compact-heading"><div><p className="eyebrow">Workspace</p><h2>Workspace details</h2></div><StatusBadge status={workspace.status}/></div><dl className="definition-list"><div><dt>Name</dt><dd>{workspace.name}</dd></div><div><dt>Your access</dt><dd>{roleLabel(workspace.role)}</dd></div><div><dt>Workspace ID</dt><dd className="monospace">{workspace.id}</dd></div></dl><p className="panel-note">Workspace editing and deletion are not exposed until tenant lifecycle and retention semantics are explicitly defined.</p></section>; }

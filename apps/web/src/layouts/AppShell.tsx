import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ChevronRight, FlaskConical } from "lucide-react";
import { BrandMark } from "../components/ui/BrandMark";
import { ErrorPanel, LoadingPanel } from "../components/ui/StateViews";
import { Icon } from "../components/ui/Icon";
import { CommandMenu } from "../components/markettwin/CommandMenu";
import { CurrentUser, Workspace, api } from "../lib/api";
import { roleLabel } from "../lib/permissions";
import { useAsync } from "../lib/useAsync";

export interface AppShellContext { user: CurrentUser; workspace: Workspace }

function breadcrumbItems(path: string) {
  const parts = path.split("/").filter(Boolean);
  const section = parts[0];
  if (section === "overview") return [{ label: "Overview", href: "/overview" }];
  if (section === "runs") return [
    { label: "Tests", href: "/runs" },
    ...(parts[1] ? [{ label: "Test", href: `/runs/${parts[1]}/overview` }] : []),
    ...(parts[2] && parts[2] !== "overview" ? [{ label: parts[2].replaceAll("-", " "), href: path }] : []),
  ];
  if (section === "targets") return [{ label: "Applications", href: "/applications" }, { label: "Target", href: `/targets/${parts[1]}` }, ...(parts[2] ? [{ label: parts[2], href: path }] : [])];
  if (section === "applications") return [{ label: "Applications", href: "/applications" }, ...(parts[1] ? [{ label: parts[1] === "new" ? "New application" : "Application", href: `/applications/${parts[1]}` }] : []), ...(parts[2] ? [{ label: parts.at(-1) === "new" ? parts[2] === "runs" ? "New test" : "New target" : parts[2] === "runs" ? "Tests" : parts[2], href: path }] : [])];
  return [{ label: "Settings", href: "/settings/profile" }, { label: parts[1] || "Profile", href: path }];
}
export function AppShell({ user, onLogout }: { user: CurrentUser; onLogout: () => Promise<void> }) {
  const location = useLocation();
  const navigate = useNavigate();
  const workspaceState = useAsync(() => api.listWorkspaces(), []);
  const [workspaceId, setWorkspaceId] = useState("");
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const previousPath = useRef(location.pathname);
  useEffect(() => {
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname;
      document.getElementById("main-content")?.focus({ preventScroll: true });
      window.scrollTo({ top: 0 });
    }
  }, [location.pathname]);
  if (workspaceState.status === "loading") return <div className="boot-screen"><BrandMark /><LoadingPanel label="Opening workspace" /></div>;
  if (workspaceState.status === "error") return <div className="boot-screen"><ErrorPanel message={workspaceState.error} action={<button className="secondary-button" onClick={() => window.location.reload()}>Try again</button>} /></div>;
  const workspace = workspaceState.data.find(item => item.id === workspaceId) ?? workspaceState.data[0];
  if (!workspace) return <div className="boot-screen"><ErrorPanel message="No workspace is available for your account. Ask your workspace administrator for access." /></div>;
  const crumbs = breadcrumbItems(location.pathname);
  return <div className="enterprise-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="sidebar">
      <Link to="/overview" className="sidebar-brand" aria-label="MarketTwin overview"><BrandMark /><div><strong>MarketTwin</strong><span>Product readiness testing</span></div></Link>
      <div className="workspace-switcher"><span className="workspace-avatar" aria-hidden="true">{workspace.name[0]?.toUpperCase()}</span><div className="workspace-copy">
        {workspaceState.data.length > 1 ? <><label className="visually-hidden" htmlFor="workspace-select">Workspace</label><select id="workspace-select" value={workspace.id} onChange={event => { setWorkspaceId(event.target.value); navigate("/overview"); }}>{workspaceState.data.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></> : <strong>{workspace.name}</strong>}
        <span>{roleLabel(workspace.role)}</span></div></div>
      <nav className="sidebar-nav" aria-label="Primary navigation">
        <NavLink to="/overview" aria-label="Overview" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon name="home" /><span>Overview</span></NavLink>
        <NavLink to="/applications" aria-label="Applications" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon name="apps" /><span>Applications</span></NavLink>
        <NavLink to="/runs" aria-label="Tests" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon name="runs" /><span>Tests</span></NavLink>
      </nav>
      <div className="sidebar-note"><FlaskConical size={19} aria-hidden="true" /><p>Different perspectives.<br />Evidence you can inspect.</p></div>
      <nav className="sidebar-nav sidebar-nav-secondary" aria-label="Workspace navigation"><NavLink to="/settings/profile" aria-label="Settings" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon name="settings" /><span>Settings</span></NavLink></nav>
      <div className="sidebar-footer"><span className="user-avatar" aria-hidden="true">{(user.display_name || user.email)[0]?.toUpperCase()}</span><div className="user-copy"><strong>{user.display_name || "Your account"}</strong><span>{user.email}</span></div><button className="icon-button" type="button" onClick={() => { setLogoutError(null); void onLogout().catch(() => setLogoutError("Could not sign out. Please try again.")); }} aria-label="Sign out"><Icon name="logout" /></button></div>
    </aside>
    <div className="content-shell"><header className="topbar"><nav className="breadcrumb" aria-label="Breadcrumb"><Link to="/overview">Workspace</Link>{crumbs.map((crumb, index) => <span key={`${crumb.href}-${index}`}><ChevronRight size={13} aria-hidden="true" />{index === crumbs.length - 1 ? <span aria-current="page">{crumb.label}</span> : <Link to={crumb.href}>{crumb.label}</Link>}</span>)}</nav><CommandMenu /></header>
      <main className="page-container" id="main-content" tabIndex={-1}>{logoutError ? <p className="form-error" role="alert">{logoutError}</p> : null}<Outlet key={workspace.id} context={{ user, workspace } satisfies AppShellContext} /></main>
    </div>
  </div>;
}

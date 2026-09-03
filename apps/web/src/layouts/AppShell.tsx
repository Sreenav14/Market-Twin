import { NavLink, Outlet, useLocation } from "react-router-dom";

import { BrandMark } from "../components/ui/BrandMark";
import { ErrorPanel, LoadingPanel } from "../components/ui/StateViews";
import { Icon } from "../components/ui/Icon";
import { CurrentUser, Workspace, api } from "../lib/api";
import { roleLabel } from "../lib/permissions";
import { useAsync } from "../lib/useAsync";

export interface AppShellContext {
  user: CurrentUser;
  workspace: Workspace;
}

export function AppShell({ user, onLogout }: { user: CurrentUser; onLogout: () => Promise<void> }) {
  const location = useLocation();
  const workspaceState = useAsync(() => api.listWorkspaces(), []);

  if (workspaceState.status === "loading") {
    return <div className="boot-screen"><BrandMark /><LoadingPanel label="Opening workspace" /></div>;
  }

  if (workspaceState.status === "error") {
    return <div className="boot-screen"><BrandMark /><ErrorPanel message={workspaceState.error} /></div>;
  }

  const workspace = workspaceState.data[0];

  if (!workspace) {
    return <div className="boot-screen"><BrandMark /><ErrorPanel message="Your account does not have access to a MarketTwin workspace." /></div>;
  }

  const breadcrumb = location.pathname === "/overview"
    ? "Overview"
    : location.pathname.split("/").filter(Boolean).map((part) => part.replaceAll("-", " ")).join(" / ");

  return (
    <div className="enterprise-shell">
      <aside className="sidebar">
        <div className="sidebar-brand"><BrandMark /><div><strong>MarketTwin</strong><span>Product testing</span></div></div>

        <div className="workspace-switcher">
          <span className="workspace-avatar">{workspace.name[0]?.toUpperCase() ?? "M"}</span>
          <div className="workspace-copy"><strong>{workspace.name}</strong><span>{roleLabel(workspace.role)}</span></div>
        </div>

        <nav className="sidebar-nav" aria-label="Primary navigation">
          <NavLink to="/overview" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon name="home" /><span>Overview</span></NavLink>
          <NavLink to="/applications" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon name="apps" /><span>Applications</span></NavLink>
          <NavLink to="/runs" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon name="runs" /><span>Runs</span></NavLink>
        </nav>

        <p className="sidebar-section-label">Workspace</p>
        <nav className="sidebar-nav sidebar-nav-secondary" aria-label="Workspace navigation">
          <NavLink to="/settings/profile" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon name="settings" /><span>Settings</span></NavLink>
        </nav>

        <div className="sidebar-footer">
          <span className="user-avatar">{(user.display_name || user.email)[0]?.toUpperCase()}</span>
          <div className="user-copy"><strong>{user.display_name || "Local user"}</strong><span>{user.email}</span></div>
          <button className="icon-button" type="button" onClick={() => void onLogout()} aria-label="Sign out"><Icon name="logout" /></button>
        </div>
      </aside>

      <div className="content-shell">
        <header className="topbar">
          <div className="breadcrumb" aria-label="Breadcrumb">{breadcrumb}</div>
          <div className="topbar-actions"><span className="environment-pill"><span />Local environment</span></div>
        </header>
        <main className="page-container" id="main-content">
          <Outlet context={{ user, workspace } satisfies AppShellContext} />
        </main>
      </div>
    </div>
  );
}

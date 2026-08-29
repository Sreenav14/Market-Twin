import { NavLink, Outlet, useOutletContext } from "react-router-dom";

import { PageHeader } from "../components/ui/PageHeader";
import { AppShellContext } from "./AppShell";

export function SettingsLayout() {
  const appContext = useOutletContext<AppShellContext>();

  return (
    <>
      <PageHeader eyebrow="Workspace" title="Settings" description="Account, workspace, membership, and security settings are separated so permissions and backend support remain explicit." />
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="Settings sections">
          <NavLink to="/settings/profile">Profile</NavLink>
          <NavLink to="/settings/workspace">Workspace</NavLink>
          <NavLink to="/settings/members">Members</NavLink>
          <NavLink to="/settings/security">Security</NavLink>
        </nav>
        <div className="settings-content"><Outlet context={appContext} /></div>
      </div>
    </>
  );
}

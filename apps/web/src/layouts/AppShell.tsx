import { useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useQueryClient } from "@tanstack/react-query";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { Menu, X } from "lucide-react";
import { BrandMark } from "../components/ui/BrandMark";
import { ErrorPanel, LoadingPanel } from "../components/ui/StateViews";
import { Icon } from "../components/ui/Icon";
import { CommandMenu } from "../components/markettwin/CommandMenu";
import { CurrentUser, Workspace, api } from "../lib/api";
import { roleLabel } from "../lib/permissions";
import { useAsync } from "../lib/useAsync";

export interface AppShellContext {
  user: CurrentUser;
  workspace: Workspace;
}

export function AppShell({
  user,
  onLogout,
}: {
  user: CurrentUser;
  onLogout: () => Promise<void>;
}) {
  const queryClient = useQueryClient();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const navigationChangedContext = useRef(false);
  const location = useLocation();
  const navigate = useNavigate();
  const workspaceState = useAsync(() => api.listWorkspaces(), []);
  const [workspaceId, setWorkspaceId] = useState("");
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const previousPath = useRef(location.pathname);

  useEffect(() => {
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname;
      navigationChangedContext.current ||= navigationOpen;
      setNavigationOpen(false);
      document.getElementById("main-content")?.focus({ preventScroll: true });
      window.scrollTo({ top: 0 });
    }
  }, [location.pathname]);

  if (workspaceState.status === "loading")
    return (
      <div className="boot-screen">
        <BrandMark />
        <LoadingPanel label="Opening workspace" />
      </div>
    );
  if (workspaceState.status === "error")
    return (
      <div className="boot-screen">
        <ErrorPanel
          message={workspaceState.error}
          action={
            <button
              className="secondary-button"
              onClick={() => window.location.reload()}
            >
              Try again
            </button>
          }
        />
      </div>
    );
  const workspace =
    workspaceState.data.find((item) => item.id === workspaceId) ??
    workspaceState.data[0];
  if (!workspace)
    return (
      <div className="boot-screen">
        <ErrorPanel message="No workspace is available for your account. Ask your workspace administrator for access." />
      </div>
    );

  const applicationTests = /^\/applications\/[^/]+\/runs(?:\/|$)/.test(location.pathname);
  const applicationsRoute = (location.pathname.startsWith("/applications") && !applicationTests) || location.pathname.startsWith("/targets/");
  const knowledgeRoute = location.pathname.startsWith("/knowledge/");

  const signOut = () => {
    setLogoutError(null);
    void onLogout().catch(() =>
      setLogoutError("Could not sign out. Please try again."),
    );
  };

  const switchWorkspace = (nextWorkspace: string) => {
    void queryClient.cancelQueries().then(() => {
      queryClient.removeQueries();
      setWorkspaceId(nextWorkspace);
      navigationChangedContext.current = true;
      setNavigationOpen(false);
      navigate("/dashboard");
    });
  };

  // Primary nav links used in both desktop topbar and mobile drawer
  const primaryLinks = (
    <nav className="topnav-links" aria-label="Primary navigation">
      <NavLink
        to="/dashboard"
        aria-label="Home"
        className={({ isActive }) => `topnav-link${isActive ? " active" : ""}`}
      >
        Home
      </NavLink>
      <Link
        to="/applications"
        aria-label="Your apps"
        aria-current={applicationsRoute ? "page" : undefined}
        className={`topnav-link${applicationsRoute ? " active" : ""}`}
      >
        Your apps
      </Link>
      <Link
        to="/runs"
        aria-label="Tests"
        aria-current={
          applicationTests || location.pathname.startsWith("/runs")
            ? "page"
            : undefined
        }
        className={`topnav-link${applicationTests || location.pathname.startsWith("/runs") ? " active" : ""}`}
      >
        Tests
      </Link>
      <Link
        to="/knowledge/review"
        aria-label="Knowledge"
        aria-current={knowledgeRoute ? "page" : undefined}
        className={`topnav-link${knowledgeRoute ? " active" : ""}`}
      >
        Knowledge
      </Link>
      <NavLink
        to="/ingestion"
        aria-label="Add knowledge"
        className={({ isActive }) => `topnav-link${isActive ? " active" : ""}`}
      >
        Add knowledge
      </NavLink>
      <NavLink
        to="/agents"
        aria-label="Testers"
        className={({ isActive }) => `topnav-link${isActive ? " active" : ""}`}
      >
        Testers
      </NavLink>
      <NavLink
        to="/settings"
        aria-label="Settings"
        className={({ isActive }) => `topnav-link${isActive ? " active" : ""}`}
      >
        Settings
      </NavLink>
    </nav>
  );

  // Workspace selector shown in both desktop and mobile
  const workspaceSelector = workspaceState.data.length > 1 ? (
    <>
      <label className="visually-hidden" htmlFor="workspace-select">Workspace</label>
      <select
        id="workspace-select"
        className="topnav-workspace-select"
        value={workspace.id}
        onChange={(e) => switchWorkspace(e.target.value)}
      >
        {workspaceState.data.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
    </>
  ) : (
    <span className="topnav-workspace-name">{workspace.name}</span>
  );

  return (
    <Dialog.Root open={navigationOpen} onOpenChange={setNavigationOpen}>
      <div className="mt-shell concept-workspace">
        <a className="skip-link" href="#main-content">
          Skip to content
        </a>

        {/* Desktop top navigation bar */}
        <header className="mt-topbar" role="banner">
          <div className="mt-topbar-inner">
            {/* Brand */}
            <Link
              to="/dashboard"
              className="mt-topbar-brand"
              aria-label="MarketTwin — Home"
            >
              <BrandMark />
              <span className="mt-topbar-wordmark">MarketTwin</span>
            </Link>

            {/* Primary nav — hidden on mobile, shown via drawer */}
            <div className="mt-topbar-nav">
              {primaryLinks}
            </div>

            {/* Workspace and account */}
            <div className="mt-topbar-end">
              <div className="mt-topbar-workspace">
                {workspaceSelector}
                <span className="mt-topbar-role">{roleLabel(workspace.role)}</span>
              </div>
              <CommandMenu />
              <button
                className="icon-button"
                type="button"
                onClick={signOut}
                aria-label="Sign out"
              >
                <Icon name="logout" />
              </button>
              {/* Mobile menu trigger */}
              <Dialog.Trigger asChild>
                <button
                  className="icon-button mt-topbar-menu-trigger"
                  aria-label="Open navigation"
                  type="button"
                >
                  <Menu size={20} aria-hidden="true" /><span>Menu</span>
                </button>
              </Dialog.Trigger>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="mt-page-content page-container" id="main-content" tabIndex={-1}>
          {logoutError ? (
            <p className="form-error" role="alert">
              {logoutError}
            </p>
          ) : null}
          <Outlet
            key={workspace.id}
            context={{ user, workspace } satisfies AppShellContext}
          />
        </main>
      </div>

      {/* Mobile navigation drawer */}
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay navigation-overlay" />
        <Dialog.Content
          className="navigation-drawer concept-workspace"
          onClick={(event) => {
            if ((event.target as HTMLElement).closest("a[href]")) {
              navigationChangedContext.current = true;
              setNavigationOpen(false);
            }
          }}
          onCloseAutoFocus={(event) => {
            if (navigationChangedContext.current) {
              event.preventDefault();
              navigationChangedContext.current = false;
              window.requestAnimationFrame(() => {
                document.getElementById("main-content")?.focus({ preventScroll: true });
              });
            }
          }}
        >
          <Dialog.Title className="visually-hidden">Workspace navigation</Dialog.Title>
          <Dialog.Description className="visually-hidden">Switch workspace or navigate MarketTwin.</Dialog.Description>
          <Dialog.Close className="icon-button navigation-close" aria-label="Close navigation">
            <X size={20} aria-hidden="true" />
          </Dialog.Close>

          {/* Drawer brand */}
          <div className="drawer-brand">
            <BrandMark />
            <div>
              <strong>MarketTwin</strong>
              <span>Testing workspace</span>
            </div>
          </div>

          {/* Drawer workspace */}
          <div className="drawer-workspace">
            {workspaceState.data.length > 1 ? (
              <>
                <label className="visually-hidden" htmlFor="mobile-workspace-select">Workspace</label>
                <select
                  id="mobile-workspace-select"
                  value={workspace.id}
                  onChange={(e) => switchWorkspace(e.target.value)}
                >
                  {workspaceState.data.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </>
            ) : (
              <strong>{workspace.name}</strong>
            )}
            <span>{roleLabel(workspace.role)}</span>
          </div>

          {/* Drawer primary nav (same links, but with icons for context) */}
          <nav className="drawer-nav" aria-label="Primary navigation">
            <NavLink to="/dashboard" aria-label="Home" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
              <Icon name="home" /><span>Home</span>
            </NavLink>
            <Link
              to="/applications"
              aria-label="Your apps"
              aria-current={applicationsRoute ? "page" : undefined}
              className={`nav-link${applicationsRoute ? " active" : ""}`}
            >
              <Icon name="apps" /><span>Your apps</span>
            </Link>
            <Link
              to="/runs"
              aria-label="Tests"
              aria-current={applicationTests || location.pathname.startsWith("/runs") ? "page" : undefined}
              className={`nav-link${applicationTests || location.pathname.startsWith("/runs") ? " active" : ""}`}
            >
              <Icon name="runs" /><span>Tests</span>
            </Link>
            <Link
              to="/knowledge/review"
              aria-label="Knowledge"
              aria-current={knowledgeRoute ? "page" : undefined}
              className={`nav-link${knowledgeRoute ? " active" : ""}`}
            >
              <Icon name="knowledge" /><span>Knowledge</span>
            </Link>
            <NavLink
              to="/agents"
              aria-label="Testers"
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              <Icon name="user" /><span>Testers</span>
            </NavLink>
            <Link
              to="/ingestion"
              aria-label="Add knowledge"
              className="nav-link"
            >
              <Icon name="ingestion" /><span>Add knowledge</span>
            </Link>
            <NavLink
              to="/settings"
              aria-label="Settings"
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              <Icon name="settings" /><span>Settings</span>
            </NavLink>
          </nav>

          {/* Drawer footer: account and sign out */}
          <div className="drawer-footer">
            <span className="user-avatar" aria-hidden="true">
              {(user.display_name || user.email)[0]?.toUpperCase()}
            </span>
            <div className="user-copy">
              <strong>{user.display_name || "Your account"}</strong>
              <span>{user.email}</span>
            </div>
            <button
              className="icon-button"
              type="button"
              onClick={signOut}
              aria-label="Sign out"
            >
              <Icon name="logout" />
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

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
import { Menu, Search, X } from "lucide-react";
import { BrandMark } from "../components/ui/BrandMark";
import { InlineAlert } from "../components/ui/Feedback";
import { ErrorPanel, LoadingPanel } from "../components/ui/StateViews";
import { Icon, type IconName } from "../components/ui/Icon";
import { Avatar } from "../components/ui/Avatar";
import { CommandMenu } from "../components/markettwin/CommandMenu";
import { NAV_COMMANDS } from "../lib/navCommands";
import { CurrentUser, Workspace, api } from "../lib/api";
import { roleLabel } from "../lib/permissions";
import { useAsync } from "../lib/useAsync";

export interface AppShellContext {
  user: CurrentUser;
  workspace: Workspace;
}

/* The primary nav, one list for the desktop sidebar and the mobile
   drawer (sidebar/buttons round): icon + label rows; the active row is
   the raised white pill. Active-state semantics are unchanged — the
   route-prefix routes (apps, tests, knowledge) keep their manual
   aria-current computation, the rest use NavLink. */
function ShellNav({
  applicationsRoute,
  knowledgeRoute,
  runsRoute,
}: {
  applicationsRoute: boolean;
  knowledgeRoute: boolean;
  runsRoute: boolean;
}) {
  const linkClass = (active: boolean) =>
    `shell-nav-link${active ? " active" : ""}`;
  /* Destinations come from the ONE registry (lib/navCommands) \u2014
     the same list the command palette runs from. */
  const activeById: Record<string, boolean | undefined> = {
    apps: applicationsRoute,
    tests: runsRoute,
    knowledge: knowledgeRoute,
  };
  const items = NAV_COMMANDS.map((command) => ({
    to: command.href,
    label: command.title,
    icon: command.icon,
    navlink: !command.activePrefixes,
    active: activeById[command.id],
  }));
  return (
    <nav className="shell-nav" aria-label="Primary navigation">
      {items.map((item) =>
        item.navlink ? (
          <NavLink
            key={item.to}
            to={item.to}
            aria-label={item.label}
            className={({ isActive }) => linkClass(isActive)}
          >
            <Icon name={item.icon} />
            <span>{item.label}</span>
          </NavLink>
        ) : (
          <Link
            key={item.to}
            to={item.to}
            aria-label={item.label}
            aria-current={item.active ? "page" : undefined}
            className={linkClass(Boolean(item.active))}
          >
            <Icon name={item.icon} />
            <span>{item.label}</span>
          </Link>
        ),
      )}
    </nav>
  );
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
  const runsRoute =
    applicationTests || location.pathname.startsWith("/runs");

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

  /* The palette lives in the sidebar; the mobile top bar opens it with
     the same synthetic ⌘K the Home heading uses. */
  const openCommandPalette = () => {
    window.dispatchEvent(
      new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }),
    );
  };

  const nav = (
    <ShellNav
      applicationsRoute={applicationsRoute}
      knowledgeRoute={knowledgeRoute}
      runsRoute={runsRoute}
    />
  );

  const userRow = (
    <>
      <Avatar kind="person" name={user.display_name || user.email} />
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
    </>
  );

  return (
    <Dialog.Root open={navigationOpen} onOpenChange={setNavigationOpen}>
      <div className="mt-shell concept-workspace">
        <a className="skip-link" href="#main-content">
          Skip to content
        </a>

        {/* Desktop sidebar: brand, palette search field, workspace,
            primary nav, account. Hidden below the shell breakpoint —
            the drawer below is its mobile form. */}
        <aside className="mt-sidebar">
          <Link
            to="/dashboard"
            className="sidebar-brand"
            aria-label="MarketTwin — Home"
          >
            <BrandMark />
            <span className="sidebar-wordmark">MarketTwin</span>
          </Link>

          <CommandMenu triggerVariant="field" />

          <div className="sidebar-workspace">
            {workspaceState.data.length > 1 ? (
              <>
                <label className="visually-hidden" htmlFor="workspace-select">
                  Workspace
                </label>
                <select
                  id="workspace-select"
                  className="sidebar-workspace-select"
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
              <span className="sidebar-workspace-name">{workspace.name}</span>
            )}
            <span className="sidebar-workspace-role">
              {roleLabel(workspace.role)}
            </span>
          </div>

          {nav}

          <div className="sidebar-user">{userRow}</div>
        </aside>

        <div className="mt-main">
          {/* Mobile top bar: brand, palette, menu trigger. */}
          <header className="mt-topbar" role="banner">
            <div className="mt-topbar-inner">
              <Link
                to="/dashboard"
                className="mt-topbar-brand"
                aria-label="MarketTwin — Home"
              >
                <BrandMark />
                <span className="mt-topbar-wordmark">MarketTwin</span>
              </Link>
              <div className="mt-topbar-end">
                <button
                  className="icon-button"
                  type="button"
                  onClick={openCommandPalette}
                  aria-label="Search pages"
                >
                  <Search size={20} aria-hidden="true" />
                </button>
                <Dialog.Trigger asChild>
                  <button
                    className="icon-button mt-topbar-menu-trigger"
                    aria-label="Open navigation"
                    type="button"
                  >
                    <Menu size={20} aria-hidden="true" />
                    <span>Menu</span>
                  </button>
                </Dialog.Trigger>
              </div>
            </div>
          </header>

          {/* Page content */}
          <main
            className="mt-page-content page-container"
            id="main-content"
            tabIndex={-1}
          >
            {logoutError ? (
              <InlineAlert severity="error" title="Could not sign out" role="alert">
                {logoutError}
              </InlineAlert>
            ) : null}
            <Outlet
              key={workspace.id}
              context={{ user, workspace } satisfies AppShellContext}
            />
          </main>
        </div>
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

          {/* Drawer primary nav (same list as the sidebar) */}
          {nav}

          {/* Drawer footer: account and sign out */}
          <div className="drawer-footer">{userRow}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

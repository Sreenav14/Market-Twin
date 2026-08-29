import {
  FormEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  BrowserRouter,
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";

import {
  ApiError,
  Application,
  CurrentUser,
  Target,
  TargetAuthorization,
  TestRun,
  Workspace,
  api,
} from "./api";

type AsyncState<T> =
  | { status: "loading"; data: null; error: null }
  | { status: "ready"; data: T; error: null }
  | { status: "error"; data: null; error: string };

function BrandMark() {
  return (
    <svg className="h-8 w-8" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="#5b67f1" />
      <path
        d="M8.5 20.5 12.8 11l3.6 6.4 2.5-4.7 4.6 7.8"
        fill="none"
        stroke="white"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone =
    normalized === "active" || normalized === "authorized" || normalized === "completed"
      ? "success"
      : normalized === "running" || normalized === "planning" || normalized === "queued"
        ? "info"
        : normalized === "failed" || normalized === "revoked"
          ? "danger"
          : "neutral";

  return <span className={`status-badge status-${tone}`}>{status.replaceAll("_", " ")}</span>;
}

function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {action ? <div className="page-action">{action}</div> : null}
    </div>
  );
}

function EmptyState({ title, copy, action }: { title: string; copy: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-orbit" aria-hidden="true"><span /><span /><span /></div>
      <h3>{title}</h3>
      <p>{copy}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

function LoadingPanel() {
  return (
    <div className="panel flex min-h-48 items-center justify-center gap-3 text-sm text-slate-500">
      <Spinner /> Loading…
    </div>
  );
}

function ErrorPanel({ message }: { message: string }) {
  return (
    <div className="error-panel" role="alert">
      <strong>We couldn’t load this view.</strong>
      <span>{message}</span>
    </div>
  );
}

function useAsync<T>(loader: () => Promise<T>, dependencies: unknown[]): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading", data: null, error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", data: null, error: null });

    loader()
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data, error: null });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: "error",
            data: null,
            error: error instanceof Error ? error.message : "Unknown error.",
          });
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);

  return state;
}

function LoginPage({ onAuthenticated }: { onAuthenticated: (user: CurrentUser) => void }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    try {
      const user = await api.login(email.trim());
      onAuthenticated(user);
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-layout">
      <header className="auth-header">
        <div className="auth-brand">
          <BrandMark />
          <span>MarketTwin</span>
        </div>
        <span className="auth-environment">Local development</span>
      </header>

      <main className="auth-main">
        <section className="auth-intro" aria-labelledby="auth-title">
          <p className="eyebrow">Product preflight</p>
          <h1 id="auth-title">Test the experience before customers do.</h1>
          <p>
            Run authorized browser studies from independent user perspectives and keep the
            resulting evidence in one workspace.
          </p>
          <div className="auth-flow" aria-label="MarketTwin workflow">
            <span>Target</span>
            <b>→</b>
            <span>Study</span>
            <b>→</b>
            <span>Evidence</span>
          </div>
        </section>

        <section className="auth-card" aria-label="Sign in">
          <div className="auth-copy">
            <h2>Sign in</h2>
            <p>Use a pre-approved local identity to open your workspace.</p>
          </div>
          <form onSubmit={submit} className="grid gap-4">
            <label className="field-label" htmlFor="email">Email</label>
            <input
              id="email"
              className="text-input"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
              autoComplete="email"
              required
            />
            {error ? <p className="form-error">{error}</p> : null}
            <button className="primary-button w-full" type="submit" disabled={busy || !email.trim()}>
              {busy ? <><Spinner /> Signing in</> : "Continue"}
            </button>
          </form>
        </section>
      </main>

      <footer className="auth-footer">Authorized targets · Independent journeys · Evidence-backed findings</footer>
    </div>
  );
}

function AppShell({ user, onLogout }: { user: CurrentUser; onLogout: () => void }) {
  const location = useLocation();
  const workspaceState = useAsync(() => api.listWorkspaces(), []);
  const workspace = workspaceState.status === "ready" ? workspaceState.data[0] : undefined;

  return (
    <div className="enterprise-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <BrandMark />
          <div><strong>MarketTwin</strong><span>Product testing</span></div>
        </div>

        <div className="workspace-switcher">
          <span className="workspace-avatar">{workspace?.name?.[0]?.toUpperCase() ?? "M"}</span>
          <div className="min-w-0 flex-1">
            <strong>{workspace?.name ?? "Workspace"}</strong>
            <span>{workspace?.role ?? "Loading access"}</span>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Primary navigation">
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <span className="nav-icon">⌂</span><span>Overview</span>
          </NavLink>
          <NavLink to="/applications" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <span className="nav-icon">◇</span><span>Applications</span>
          </NavLink>
          <NavLink to="/runs" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <span className="nav-icon">▶</span><span>Runs</span>
          </NavLink>
        </nav>

        <div className="sidebar-section-label">Workspace</div>
        <nav className="sidebar-nav">
          <NavLink to="/settings" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <span className="nav-icon">⚙</span><span>Settings</span>
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <div className="user-avatar">{(user.display_name || user.email)[0]?.toUpperCase()}</div>
          <div className="min-w-0 flex-1">
            <strong>{user.display_name || "Local user"}</strong>
            <span>{user.email}</span>
          </div>
          <button className="icon-button" type="button" onClick={onLogout} aria-label="Sign out">↗</button>
        </div>
      </aside>

      <div className="content-shell">
        <header className="topbar">
          <div className="breadcrumb">{location.pathname === "/" ? "Overview" : location.pathname.split("/").filter(Boolean).join(" / ")}</div>
          <div className="topbar-actions">
            <span className="environment-pill"><span />Local environment</span>
            <Link className="primary-button compact" to="/applications">New study</Link>
          </div>
        </header>
        <div className="page-container">
          <Routes>
            <Route path="/" element={<OverviewPage workspace={workspace} />} />
            <Route path="/applications" element={<ApplicationsPage workspace={workspace} />} />
            <Route path="/applications/:applicationId" element={<ApplicationDetailPage />} />
            <Route path="/applications/:applicationId/targets/new" element={<NewTargetPage />} />
            <Route path="/targets/:targetId/authorization" element={<AuthorizationPage />} />
            <Route path="/applications/:applicationId/runs/new" element={<NewRunPage />} />
            <Route path="/runs" element={<RunsPage workspace={workspace} />} />
            <Route path="/runs/:runId" element={<RunDetailPage />} />
            <Route path="/settings" element={<SettingsPage user={user} workspace={workspace} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}

function OverviewPage({ workspace }: { workspace?: Workspace }) {
  const applicationsState = useAsync(
    () => (workspace ? api.listApplications(workspace.id) : Promise.resolve([] as Application[])),
    [workspace?.id],
  );

  if (applicationsState.status === "loading") return <LoadingPanel />;
  if (applicationsState.status === "error") return <ErrorPanel message={applicationsState.error} />;

  const applications = applicationsState.data;

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Overview"
        description="Configure authorized product targets, create studies, and review testing activity from one place."
        action={<Link className="primary-button" to="/applications">Start a study</Link>}
      />

      <div className="metric-grid">
        <div className="metric-card accent-indigo"><span>Applications</span><strong>{applications.length}</strong><small>Products in this workspace</small></div>
        <div className="metric-card accent-cyan"><span>Workspace</span><strong>{workspace?.status ?? "—"}</strong><small>{workspace?.role ? `${workspace.role} access` : "Loading access"}</small></div>
        <div className="metric-card accent-emerald"><span>Perspectives</span><strong>Dynamic</strong><small>Generated for each study</small></div>
      </div>

      <section className="section-block">
        <div className="section-heading"><div><p className="eyebrow">Products</p><h2>Applications</h2></div><Link className="text-link" to="/applications">View all →</Link></div>
        {applications.length === 0 ? (
          <EmptyState title="Add your first application" copy="Applications group the product targets and studies your team evaluates." action={<Link className="secondary-button" to="/applications">Add application</Link>} />
        ) : (
          <div className="card-grid">
            {applications.slice(0, 4).map((application, index) => (
              <Link className="product-card" to={`/applications/${application.id}`} key={application.id}>
                <span className={`product-icon product-icon-${index % 4}`}>{application.name.slice(0, 2).toUpperCase()}</span>
                <div><strong>{application.name}</strong><p>{application.description || "No description yet."}</p></div>
                <span className="card-arrow">→</span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function ApplicationsPage({ workspace }: { workspace?: Workspace }) {
  const [revision, setRevision] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const state = useAsync(
    () => (workspace ? api.listApplications(workspace.id) : Promise.resolve([] as Application[])),
    [workspace?.id, revision],
  );

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace) return;
    setBusy(true); setError(null);
    try {
      await api.createApplication(workspace.id, name.trim(), description.trim());
      setName(""); setDescription(""); setShowForm(false); setRevision((value) => value + 1);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Could not create application.");
    } finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader eyebrow="Products" title="Applications" description="Organize the products and environments your team is authorized to evaluate." action={<button className="primary-button" type="button" onClick={() => setShowForm(true)}>+ Add application</button>} />
      {showForm ? (
        <div className="panel mb-6">
          <form className="form-grid" onSubmit={create}>
            <div className="form-heading"><div><h2>New application</h2><p>Create a product container before adding test targets.</p></div><button className="icon-button" type="button" onClick={() => setShowForm(false)}>×</button></div>
            <label className="field-label" htmlFor="app-name">Name</label>
            <input id="app-name" className="text-input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Acme Checkout" required maxLength={200} />
            <label className="field-label" htmlFor="app-description">Description <span>Optional</span></label>
            <textarea id="app-description" className="text-area" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What part of the product will your team evaluate?" rows={3} />
            {error ? <p className="form-error">{error}</p> : null}
            <div className="form-actions"><button className="secondary-button" type="button" onClick={() => setShowForm(false)}>Cancel</button><button className="primary-button" disabled={busy || !name.trim()}>{busy ? <><Spinner /> Creating</> : "Create application"}</button></div>
          </form>
        </div>
      ) : null}
      {state.status === "loading" ? <LoadingPanel /> : state.status === "error" ? <ErrorPanel message={state.error} /> : state.data.length === 0 ? <EmptyState title="No applications yet" copy="Create an application to organize targets and studies." /> : <div className="data-list">{state.data.map((application, index) => <Link to={`/applications/${application.id}`} className="data-row" key={application.id}><span className={`product-icon product-icon-${index % 4}`}>{application.name.slice(0, 2).toUpperCase()}</span><div className="row-primary"><strong>{application.name}</strong><span>{application.description || "No description"}</span></div><StatusBadge status={application.status} /><span className="card-arrow">→</span></Link>)}</div>}
    </>
  );
}

function ApplicationDetailPage() {
  const { applicationId = "" } = useParams();
  const appState = useAsync(() => api.getApplication(applicationId), [applicationId]);
  const targetsState = useAsync(() => api.listTargets(applicationId), [applicationId]);
  const runsState = useAsync(() => api.listRuns(applicationId), [applicationId]);

  if (appState.status === "loading") return <LoadingPanel />;
  if (appState.status === "error") return <ErrorPanel message={appState.error} />;

  const application = appState.data;
  const targets = targetsState.status === "ready" ? targetsState.data : [];
  const runs = runsState.status === "ready" ? runsState.data : [];

  return (
    <>
      <PageHeader eyebrow="Application" title={application.name} description={application.description || "Configure authorized targets and run user-perspective studies against this product."} action={<Link className="primary-button" to={`/applications/${application.id}/runs/new`}>New study</Link>} />
      <div className="tab-strip"><span className="active">Overview</span><span>Targets <b>{targets.length}</b></span><span>Runs <b>{runs.length}</b></span></div>
      <section className="section-block">
        <div className="section-heading"><div><p className="eyebrow">Environments</p><h2>Targets</h2></div><Link className="secondary-button compact" to={`/applications/${application.id}/targets/new`}>+ Add target</Link></div>
        {targetsState.status === "loading" ? <LoadingPanel /> : targets.length === 0 ? <EmptyState title="No targets configured" copy="Add a local, staging, QA, demo, or production URL before running a study." action={<Link className="primary-button" to={`/applications/${application.id}/targets/new`}>Add target</Link>} /> : <div className="data-list">{targets.map((target) => <div className="data-row" key={target.id}><span className="target-icon">⌁</span><div className="row-primary"><strong>{target.name}</strong><span>{target.base_url}</span></div><span className="environment-label">{target.environment}</span><Link className="text-link" to={`/targets/${target.id}/authorization`}>Authorization →</Link></div>)}</div>}
      </section>
      <section className="section-block">
        <div className="section-heading"><div><p className="eyebrow">Activity</p><h2>Recent runs</h2></div></div>
        {runsState.status === "loading" ? <LoadingPanel /> : runs.length === 0 ? <EmptyState title="No studies for this application" copy="Create a study once an authorized target is ready." /> : <div className="data-list">{runs.slice(0, 5).map((run) => <Link className="data-row" to={`/runs/${run.id}`} key={run.id}><span className="run-icon">▶</span><div className="row-primary"><strong>{String(run.configuration_snapshot.study_brief ?? "Untitled study")}</strong><span>{String(run.target_snapshot.base_url ?? "Target")}</span></div><StatusBadge status={run.status} /><span className="card-arrow">→</span></Link>)}</div>}
      </section>
    </>
  );
}

function NewTargetPage() {
  const { applicationId = "" } = useParams();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [environment, setEnvironment] = useState("local");
  const [baseUrl, setBaseUrl] = useState("http://localhost:3000/");
  const [requiresAuth, setRequiresAuth] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const target = await api.createTarget(applicationId, { name: name.trim(), environment, base_url: baseUrl.trim(), requires_auth: requiresAuth });
      navigate(`/targets/${target.id}/authorization`);
    } catch (submitError) { setError(submitError instanceof Error ? submitError.message : "Could not create target."); }
    finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader eyebrow="Application target" title="Add an environment" description="Tell MarketTwin where this application is available. The backend derives the initial allowed origin from the URL." />
      <div className="two-column-layout">
        <form className="panel form-grid" onSubmit={submit}>
          <label className="field-label" htmlFor="target-name">Target name</label><input id="target-name" className="text-input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Local storefront" required />
          <label className="field-label" htmlFor="environment">Environment</label><select id="environment" className="text-input" value={environment} onChange={(event) => setEnvironment(event.target.value)}><option value="local">Local</option><option value="development">Development</option><option value="staging">Staging</option><option value="qa">QA</option><option value="demo">Demo</option><option value="production">Production</option></select>
          <label className="field-label" htmlFor="base-url">Base URL</label><input id="base-url" className="text-input" type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} required />
          <label className="toggle-row"><span><strong>Protected experience</strong><small>This target requires login or another authentication step.</small></span><input type="checkbox" checked={requiresAuth} onChange={(event) => setRequiresAuth(event.target.checked)} /></label>
          {error ? <p className="form-error">{error}</p> : null}
          <div className="form-actions"><button className="secondary-button" type="button" onClick={() => navigate(-1)}>Cancel</button><button className="primary-button" disabled={busy || !name.trim() || !baseUrl.trim()}>{busy ? <><Spinner /> Saving</> : "Save target"}</button></div>
        </form>
        <aside className="insight-card"><span className="insight-icon">◎</span><h3>Network policy</h3><p>MarketTwin stores the target origin separately and the browser runtime enforces deterministic network policy before navigation and requests.</p></aside>
      </div>
    </>
  );
}

function AuthorizationPage() {
  const { targetId = "" } = useParams();
  const [revision, setRevision] = useState(0);
  const targetState = useAsync(() => api.getTarget(targetId), [targetId]);
  const authorizationState = useAsync(async () => {
    try { return await api.getAuthorization(targetId); }
    catch (error) { if (error instanceof ApiError && error.status === 404) return null; throw error; }
  }, [targetId, revision]);
  const [basis, setBasis] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function authorize(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    try { await api.authorizeTarget(targetId, basis.trim()); setRevision((value) => value + 1); }
    catch (submitError) { setError(submitError instanceof Error ? submitError.message : "Could not authorize target."); }
    finally { setBusy(false); }
  }

  async function revoke() {
    setBusy(true); setError(null);
    try { await api.revokeAuthorization(targetId); setRevision((value) => value + 1); }
    catch (submitError) { setError(submitError instanceof Error ? submitError.message : "Could not revoke authorization."); }
    finally { setBusy(false); }
  }

  if (targetState.status === "loading" || authorizationState.status === "loading") return <LoadingPanel />;
  if (targetState.status === "error") return <ErrorPanel message={targetState.error} />;
  if (authorizationState.status === "error") return <ErrorPanel message={authorizationState.error} />;
  const target = targetState.data;
  const authorization = authorizationState.data;
  const active = authorization?.status === "authorized";

  return (
    <>
      <PageHeader eyebrow="Target authorization" title={target.name} description={target.base_url} />
      <div className="two-column-layout">
        <section className="panel">
          <div className="authorization-status"><span className={`authorization-orb ${active ? "active" : ""}`}>{active ? "✓" : "!"}</span><div><p className="eyebrow">Current state</p><h2>{active ? "Authorized for testing" : "Authorization required"}</h2><p>{active ? "MarketTwin may create studies against this target while authorization remains active." : "An owner or admin must explicitly confirm permission before MarketTwin can create a test run."}</p></div></div>
          {active && authorization ? <div className="audit-box"><div><span>Authorized</span><strong>{authorization.authorized_at ? new Date(authorization.authorized_at).toLocaleString() : "Active"}</strong></div><div><span>Basis</span><strong>{authorization.authorization_basis}</strong></div></div> : <form className="form-grid mt-6" onSubmit={authorize}><label className="field-label" htmlFor="basis">Why are you authorized to test this target?</label><textarea id="basis" className="text-area" rows={4} value={basis} onChange={(event) => setBasis(event.target.value)} placeholder="For example: This staging environment is owned and operated by our team for internal product testing." minLength={10} maxLength={2000} required /><label className="confirmation-row"><input type="checkbox" required /><span>I confirm that I own this target or have permission to test it.</span></label>{error ? <p className="form-error">{error}</p> : null}<button className="primary-button justify-self-start" disabled={busy || basis.trim().length < 10}>{busy ? <><Spinner /> Authorizing</> : "Authorize target"}</button></form>}
          {active ? <button className="danger-button mt-6" type="button" onClick={revoke} disabled={busy}>Revoke authorization</button> : null}
        </section>
        <aside className="insight-card"><span className="insight-icon">◎</span><h3>Authorization is live state</h3><p>A past authorization is kept for audit, but MarketTwin rechecks current authorization before creating a test run.</p></aside>
      </div>
    </>
  );
}

function NewRunPage() {
  const { applicationId = "" } = useParams();
  const navigate = useNavigate();
  const targetsState = useAsync(() => api.listTargets(applicationId), [applicationId]);
  const [targetId, setTargetId] = useState("");
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (targetsState.status === "ready" && !targetId && targetsState.data.length > 0) setTargetId(targetsState.data[0].id);
  }, [targetId, targetsState]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    try { const run = await api.createRun(applicationId, targetId, brief.trim()); navigate(`/runs/${run.id}`); }
    catch (submitError) { setError(submitError instanceof Error ? submitError.message : "Could not create study."); }
    finally { setBusy(false); }
  }

  if (targetsState.status === "loading") return <LoadingPanel />;
  if (targetsState.status === "error") return <ErrorPanel message={targetsState.error} />;

  return (
    <>
      <PageHeader eyebrow="New study" title="What do you want to learn?" description="Describe the product outcome you care about. MarketTwin will generate relevant perspectives and missions dynamically when planning is connected." />
      <div className="study-composer">
        <form onSubmit={submit}>
          <div className="composer-target"><label htmlFor="study-target">Target</label><select id="study-target" value={targetId} onChange={(event) => setTargetId(event.target.value)} disabled={targetsState.data.length === 0}>{targetsState.data.length === 0 ? <option>No targets available</option> : targetsState.data.map((target) => <option value={target.id} key={target.id}>{target.name} · {target.environment}</option>)}</select></div>
          <div className="composer-body"><textarea value={brief} onChange={(event) => setBrief(event.target.value)} placeholder="Check whether first-time customers can understand our pricing and confidently choose the right plan." maxLength={4000} rows={7} aria-label="Testing goal" /><div className="composer-meta"><span>Focus on the decision or outcome, not step-by-step instructions.</span><span>{brief.length}/4000</span></div></div>
          {error ? <div className="composer-error">{error}</div> : null}
          <div className="composer-footer"><div className="dynamic-note"><span className="spark">•</span><span>Perspectives and missions are generated dynamically for this study.</span></div><button className="primary-button" disabled={busy || !targetId || brief.trim().length < 10}>{busy ? <><Spinner /> Creating</> : "Create study →"}</button></div>
        </form>
      </div>
    </>
  );
}

function RunsPage({ workspace }: { workspace?: Workspace }) {
  const applicationsState = useAsync(() => workspace ? api.listApplications(workspace.id) : Promise.resolve([] as Application[]), [workspace?.id]);
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [loadingRuns, setLoadingRuns] = useState(true);

  useEffect(() => {
    if (applicationsState.status !== "ready") return;
    let cancelled = false;
    setLoadingRuns(true);
    Promise.all(applicationsState.data.map((application) => api.listRuns(application.id)))
      .then((groups) => { if (!cancelled) setRuns(groups.flat()); })
      .finally(() => { if (!cancelled) setLoadingRuns(false); });
    return () => { cancelled = true; };
  }, [applicationsState]);

  return (
    <>
      <PageHeader eyebrow="Testing activity" title="Runs" description="Track studies across the workspace and open the exact target snapshot and configuration used for each one." />
      {applicationsState.status === "loading" || loadingRuns ? <LoadingPanel /> : applicationsState.status === "error" ? <ErrorPanel message={applicationsState.error} /> : runs.length === 0 ? <EmptyState title="No runs yet" copy="Open an application and create your first study." action={<Link className="primary-button" to="/applications">Choose application</Link>} /> : <div className="data-list">{runs.map((run) => <Link className="data-row" to={`/runs/${run.id}`} key={run.id}><span className="run-icon">▶</span><div className="row-primary"><strong>{String(run.configuration_snapshot.study_brief ?? "Untitled study")}</strong><span>{String(run.target_snapshot.name ?? run.target_snapshot.base_url ?? "Target")}</span></div><StatusBadge status={run.status} /><span className="card-arrow">→</span></Link>)}</div>}
    </>
  );
}

function RunDetailPage() {
  const { runId = "" } = useParams();
  const runState = useAsync(() => api.getRun(runId), [runId]);
  if (runState.status === "loading") return <LoadingPanel />;
  if (runState.status === "error") return <ErrorPanel message={runState.error} />;
  const run = runState.data;
  const brief = String(run.configuration_snapshot.study_brief ?? "Untitled study");

  return (
    <>
      <PageHeader eyebrow="Study" title={brief} description={String(run.target_snapshot.base_url ?? "")} action={<StatusBadge status={run.status} />} />
      <div className="run-hero"><div className="run-progress-line"><span className="complete" /><span /><span /><span /></div><div className="run-stage-grid"><div><strong>Created</strong><span>Study saved</span></div><div><strong>Planning</strong><span>Not connected yet</span></div><div><strong>Execution</strong><span>Waiting</span></div><div><strong>Findings</strong><span>Waiting</span></div></div></div>
      <div className="two-column-layout mt-6">
        <section className="panel"><div className="section-heading"><div><p className="eyebrow">Configuration</p><h2>Study details</h2></div></div><dl className="definition-list"><div><dt>Status</dt><dd><StatusBadge status={run.status} /></dd></div><div><dt>Target</dt><dd>{String(run.target_snapshot.name ?? "Target")}</dd></div><div><dt>Environment</dt><dd>{String(run.target_snapshot.environment ?? "—")}</dd></div><div><dt>Authentication</dt><dd>{run.target_snapshot.requires_auth ? "Protected" : "Public"}</dd></div></dl></section>
        <aside className="insight-card"><span className="insight-icon">i</span><h3>Planning is the next backend milestone</h3><p>This run is persisted by the current Control API. Dynamic personas, missions, journeys, browser execution, and evidence will populate this page as those backend stages are connected.</p></aside>
      </div>
    </>
  );
}

function SettingsPage({ user, workspace }: { user: CurrentUser; workspace?: Workspace }) {
  return (
    <>
      <PageHeader eyebrow="Workspace" title="Settings" description="Current account and workspace context. Additional configuration should appear only when the backend supports it." />
      <div className="panel"><dl className="definition-list"><div><dt>User</dt><dd>{user.display_name || user.email}</dd></div><div><dt>Email</dt><dd>{user.email}</dd></div><div><dt>Workspace</dt><dd>{workspace?.name ?? "—"}</dd></div><div><dt>Role</dt><dd>{workspace?.role ?? "—"}</dd></div><div><dt>Environment</dt><dd><span className="environment-pill"><span />Local</span></dd></div></dl></div>
    </>
  );
}

function AppRoot() {
  const [session, setSession] = useState<AsyncState<CurrentUser>>({ status: "loading", data: null, error: null });

  const resolveSession = useCallback(() => {
    setSession({ status: "loading", data: null, error: null });
    api.me()
      .then((user) => setSession({ status: "ready", data: user, error: null }))
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 401) {
          setSession({ status: "error", data: null, error: "unauthenticated" });
        } else {
          setSession({ status: "error", data: null, error: error instanceof Error ? error.message : "Unable to connect." });
        }
      });
  }, []);

  useEffect(resolveSession, [resolveSession]);

  async function logout() {
    await api.logout();
    setSession({ status: "error", data: null, error: "unauthenticated" });
  }

  if (session.status === "loading") {
    return <div className="boot-screen"><BrandMark /><Spinner /><span>Opening MarketTwin…</span></div>;
  }

  if (session.status === "error") {
    if (session.error !== "unauthenticated") {
      return <div className="boot-screen"><BrandMark /><ErrorPanel message={session.error} /><button className="secondary-button" onClick={resolveSession}>Try again</button></div>;
    }
    return <LoginPage onAuthenticated={(user) => setSession({ status: "ready", data: user, error: null })} />;
  }

  return <AppShell user={session.data} onLogout={logout} />;
}

export function App() {
  return <BrowserRouter><AppRoot /></BrowserRouter>;
}

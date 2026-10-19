import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import { Spinner } from "../../components/ui/StateViews";
import { api } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { AppShellContext } from "../../layouts/AppShell";

function validateTargetUrl(rawUrl: string): string | null {
  const trimmed = rawUrl.trim();
  if (!trimmed) return "Base URL is required.";
  if (trimmed.includes("*")) {
    return "Wildcards (e.g. *.example.com) are not supported. Enter an exact hostname.";
  }
  if (!/^https?:\/\//i.test(trimmed)) {
    return "Base URL must start with http:// or https://.";
  }
  try {
    const parsed = new URL(trimmed);
    if (!parsed.hostname) {
      return "URL must contain a valid hostname or IP address.";
    }
  } catch {
    return "Please enter a valid absolute URL (e.g. http://localhost:3000/ or https://staging.example.com).";
  }
  return null;
}

export function NewTargetPage() {
  const { applicationId = "" } = useParams();
  const navigate = useNavigate();
  const { workspace } = useOutletContext<AppShellContext>();
  const [name, setName] = useState("");
  const [environment, setEnvironment] = useState("local");
  const [baseUrl, setBaseUrl] = useState("http://localhost:3000/");
  const [requiresAuth, setRequiresAuth] = useState(false);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  if (!canWriteWorkspace(workspace.role)) {
    return (
      <>
        <PageHeader eyebrow="Target" title="Add environment" />
        <div className="error-panel" role="alert">
          <div>
            <strong>Read-only workspace</strong>
            <span>Your workspace role ({workspace.role}) cannot create targets.</span>
          </div>
          <div>
            <Link
              className="secondary-button"
              to={`/applications/${applicationId}/targets`}
            >
              Back to targets
            </Link>
          </div>
        </div>
      </>
    );
  }

  const nameError = touched && !name.trim() ? "Target name is required." : null;
  const urlError = touched ? validateTargetUrl(baseUrl) : null;

  let pathNotice: string | null = null;
  try {
    const parsed = new URL(baseUrl.trim());
    if (parsed.pathname && parsed.pathname !== "/" && parsed.pathname !== "") {
      pathNotice = `MarketTwin derives the execution origin (${parsed.origin}) from this URL. Specific subpaths do not restrict network origin permissions.`;
    }
  } catch {
    // validation will catch invalid URLs
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setTouched(true);

    const validation = validateTargetUrl(baseUrl);
    if (!name.trim() || validation) {
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const target = await api.createTarget(applicationId, {
        name: name.trim(),
        environment,
        base_url: baseUrl.trim(),
        requires_auth: requiresAuth,
      });
      if (mounted.current) navigate(`/targets/${target.id}/authorization`);
    } catch (submitError) {
      if (mounted.current) setError(
        submitError instanceof Error
          ? submitError.message
          : "Could not create target.",
      );
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Application target"
        title="Add environment"
        description="Creating an environment does not authorize a browser to test it. You will review and authorize the execution scope in the next step."
      />
      <div className="two-column-layout">
        <form className="panel form-grid" onSubmit={submit} noValidate>
          <div>
            <label className="field-label" htmlFor="target-name">
              Target name <span aria-hidden="true" style={{ color: "var(--danger)" }}>*</span>
            </label>
            <input
              id="target-name"
              className="text-input"
              value={name}
              disabled={busy}
              onChange={(event) => {
                setName(event.target.value);
                setError(null);
              }}
              onBlur={() => setTouched(true)}
              placeholder="e.g. Local storefront or Staging cluster"
              required
              autoFocus
              aria-invalid={nameError ? "true" : "false"}
              aria-describedby={nameError ? "target-name-error" : undefined}
            />
            {nameError ? (
              <p
                id="target-name-error"
                className="form-error"
                role="alert"
                style={{ marginTop: "4px" }}
              >
                {nameError}
              </p>
            ) : null}
          </div>

          <div>
            <label className="field-label" htmlFor="environment">
              Environment
            </label>
            <select
              id="environment"
              className="text-input"
              value={environment}
              disabled={busy}
              onChange={(event) => setEnvironment(event.target.value)}
            >
              <option value="local">Local (http://localhost, 127.0.0.1)</option>
              <option value="development">Development</option>
              <option value="qa">QA</option>
              <option value="staging">Staging</option>
              <option value="demo">Demo</option>
              <option value="production">Production</option>
            </select>
          </div>

          <div>
            <label className="field-label" htmlFor="base-url">
              Base URL <span aria-hidden="true" style={{ color: "var(--danger)" }}>*</span>
            </label>
            <input
              id="base-url"
              className="text-input"
              type="url"
              value={baseUrl}
              disabled={busy}
              onChange={(event) => {
                setBaseUrl(event.target.value);
                setError(null);
              }}
              onBlur={() => setTouched(true)}
              placeholder="https://staging.example.com/"
              required
              spellCheck={false}
              aria-invalid={urlError ? "true" : "false"}
              aria-describedby={urlError ? "base-url-error" : undefined}
            />
            {urlError ? (
              <p
                id="base-url-error"
                className="form-error"
                role="alert"
                style={{ marginTop: "4px" }}
              >
                {urlError}
              </p>
            ) : null}
            {pathNotice && !urlError ? (
              <p className="panel-note" style={{ marginTop: "4px" }}>
                {pathNotice}
              </p>
            ) : null}
          </div>

          <label className="toggle-row">
            <span>
              <strong>Protected experience (requires login)</strong>
              <small>
                Enable this if test journeys must pass authentication screens. Agents will coordinate with human assistance or use configured credentials. Identity provider origins (e.g. OAuth/SSO) must still be authorized in network policy.
              </small>
            </span>
            <input
              type="checkbox"
              checked={requiresAuth}
              disabled={busy}
              onChange={(event) => setRequiresAuth(event.target.checked)}
            />
          </label>

          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}

          <div className="form-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={() => navigate(-1)}
              disabled={busy}
            >
              Cancel
            </button>
            <button
              className="primary-button"
              type="submit"
              disabled={busy || !name.trim() || !baseUrl.trim()}
            >
              {busy ? (
                <>
                  <Spinner /> Saving target…
                </>
              ) : (
                "Save target & review authorization"
              )}
            </button>
          </div>
        </form>

        <aside className="info-card">
          <span className="info-icon">
            <Icon name="shield" size={18} />
          </span>
          <h2>Two-step security boundary</h2>
          <p>
            <strong>Creating an environment does not authorize testing.</strong>
          </p>
          <p style={{ marginTop: "10px" }}>
            MarketTwin derives the initial allowed origin from the base URL scheme, host, and port.
          </p>
          <p style={{ marginTop: "10px" }}>
            Subdomains and external identity providers stay strictly blocked until explicitly requested in network policy.
          </p>
          <p style={{ marginTop: "10px" }}>
            In the next step, an authorized owner or admin must sign off on the testing scope before tests can execute.
          </p>
        </aside>
      </div>
    </>
  );
}

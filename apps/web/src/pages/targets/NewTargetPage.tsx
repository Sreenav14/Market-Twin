import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";
import { ErrorSummary, FieldError, RequiredLegend, RequiredMark } from "../../components/ui/Field";
import { Checkbox } from "../../components/ui/Choice";
import { InlineAlert } from "../../components/ui/Feedback";
import { PageHeader } from "../../components/ui/PageHeader";
import { Spinner } from "../../components/ui/StateViews";
import { api } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { AppShellContext } from "../../layouts/AppShell";

function validateTargetUrl(rawUrl: string): string | null {
  const trimmed = rawUrl.trim();
  if (!trimmed) return "Enter a base URL, for example https://staging.example.com.";
  if (trimmed.includes("*")) {
    return "Wildcards (e.g. *.example.com) are not supported. Enter an exact hostname.";
  }
  if (!/^https?:\/\//i.test(trimmed)) {
    return "Enter a base URL starting with http:// or https://.";
  }
  try {
    const parsed = new URL(trimmed);
    if (!parsed.hostname) {
      return "URL must contain a valid hostname or IP address.";
    }
  } catch {
    return "Enter a valid absolute URL, for example http://localhost:3000/ or https://staging.example.com.";
  }
  return null;
}

export function NewTargetPage() {
  const { applicationId = "" } = useParams();
  const navigate = useNavigate();
  const [parameters] = useSearchParams();
  const { workspace } = useOutletContext<AppShellContext>();
  const [name, setName] = useState("");
  const [environment, setEnvironment] = useState("local");
  const [baseUrl, setBaseUrl] = useState(parameters.get("url") ?? "http://localhost:3000/");
  const [requiresAuth, setRequiresAuth] = useState(false);
  // Punish late, reward early (Spec 3 §6.2): errors show per-field on
  // blur or on submit, and clear instantly once the value is fixed
  // because they are derived from the current value.
  const [touched, setTouched] = useState<ReadonlySet<string>>(new Set());
  const [submitted, setSubmitted] = useState(false);
  const blur = (field: string) => setTouched((prev) => new Set(prev).add(field));
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
        <PageHeader eyebrow="Target" title="Add target" />
        <InlineAlert severity="warning" title="Read-only workspace" action={<Link
              className="secondary-button"
              to={`/applications/${applicationId}/targets`}
            >
              Back to targets
            </Link>}>Your workspace role ({workspace.role}) cannot create targets.</InlineAlert>
      </>
    );
  }

  const show = (field: string) => submitted || touched.has(field);
  const nameError = show("name") && !name.trim() ? "Enter a target name." : null;
  const urlError = show("url") ? validateTargetUrl(baseUrl) : null;
  const summaryErrors = [
    ...(name.trim() ? [] : [{ targetId: "target-name", message: "Enter a target name." }]),
    ...(validateTargetUrl(baseUrl) ? [{ targetId: "base-url", message: validateTargetUrl(baseUrl)! }] : []),
  ];

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
    setSubmitted(true);

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
        title="Add target"
        description="Creating a target does not authorize a browser to test it. You will review and authorize the execution scope in the next step."
      />
      <div className="two-column-layout">
        <form className="panel form-grid" onSubmit={submit} noValidate>
          {submitted && summaryErrors.length ? <ErrorSummary errors={summaryErrors} /> : null}
          <RequiredLegend />
          <div>
            <label className="field-label" htmlFor="target-name">
              Target name <RequiredMark required />
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
              onBlur={() => blur("name")}
              placeholder="e.g. Local storefront or Staging cluster"
              required
              autoFocus
              aria-invalid={nameError ? true : undefined}
              aria-describedby={nameError ? "target-name-error" : undefined}
            />
            {nameError ? <FieldError id="target-name-error">{nameError}</FieldError> : null}
          </div>

          <div>
            <label className="field-label" htmlFor="environment">
              Environment <RequiredMark required={false} />
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
              Base URL <RequiredMark required />
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
              onBlur={() => blur("url")}
              placeholder="https://staging.example.com/"
              required
              spellCheck={false}
              aria-invalid={urlError ? true : undefined}
              aria-describedby={urlError ? "base-url-error" : undefined}
            />
            {urlError ? <FieldError id="base-url-error">{urlError}</FieldError> : null}
            {pathNotice && !urlError ? (
              <p className="panel-note" style={{ marginTop: "4px" }}>
                {pathNotice}
              </p>
            ) : null}
          </div>

          {/* Was a switch-shaped .toggle-row; the value is saved
              with the form (createTarget), nothing applies on flip —
              so it is a checkbox, not a switch (Spec 3 §4 ruling). */}
          <Checkbox
            checked={requiresAuth}
            disabled={busy}
            onChange={(event) => setRequiresAuth(event.target.checked)}
            label={<strong>Protected experience (requires login)</strong>}
            hint="Enable this if test journeys must pass authentication screens. Testers will coordinate with human assistance or use configured credentials. Identity provider origins (e.g. OAuth/SSO) must still be authorized in network policy."
          />

          {error ? (
            <InlineAlert severity="error" title="Could not create target" role="alert">
              {error}
            </InlineAlert>
          ) : null}

          <div className="form-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={() => navigate(`/applications/${applicationId}/targets`)}
              disabled={busy}
            >
              Cancel
            </button>
            <button
              className="primary-button"
              type="submit"
              disabled={busy}
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
            <Icon name="shield" size={20} />
          </span>
          <h2>Two-step security boundary</h2>
          <p>
            <strong>Creating a target does not authorize testing.</strong>
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

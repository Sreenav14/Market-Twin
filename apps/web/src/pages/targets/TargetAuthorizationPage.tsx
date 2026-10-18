import { FormEvent, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";

import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import {
  ErrorPanel,
  LoadingPanel,
  Spinner,
} from "../../components/ui/StateViews";
import { ApiError, TargetAuthorization, api } from "../../lib/api";
import { canAuthorizeTarget } from "../../lib/permissions";
import { isAuthorizationActive } from "../../lib/targetAuthorization";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

export function TargetAuthorizationPage() {
  const { targetId = "" } = useParams();
  const { workspace } = useOutletContext<AppShellContext>();
  const [revision, setRevision] = useState(0);
  const targetState = useAsync(() => api.getTarget(targetId), [targetId]);
  const authorizationState = useAsync<TargetAuthorization | null>(async () => {
    try {
      return await api.getAuthorization(targetId);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  }, [targetId, revision]);
  const [basis, setBasis] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (
    targetState.status === "loading" ||
    authorizationState.status === "loading"
  )
    return <LoadingPanel label="Loading authorization" />;
  if (targetState.status === "error")
    return <ErrorPanel message={targetState.error} />;
  if (authorizationState.status === "error")
    return <ErrorPanel message={authorizationState.error} />;

  const target = targetState.data;
  const authorization = authorizationState.data;
  const active = isAuthorizationActive(authorization);
  const expired = authorization?.status === "authorized" && !active;
  const mayAuthorize =
    canAuthorizeTarget(workspace.role) && target.status === "active";

  async function authorize(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.authorizeTarget(targetId, basis.trim());
      setBasis("");
      setConfirmed(false);
      setRevision((value) => value + 1);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Could not authorize target.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function revoke() {
    setBusy(true);
    setError(null);
    try {
      await api.revokeAuthorization(targetId);
      setRevision((value) => value + 1);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Could not revoke authorization.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Target authorization"
        title={target.name}
        description={`${target.environment} · ${target.base_url}`}
        action={
          <Link className="secondary-button" to={`/targets/${target.id}`}>
            Target details
          </Link>
        }
      />
      <div className="two-column-layout">
        <section className="panel">
          <div className="authorization-status">
            <span className={`authorization-orb ${active ? "active" : ""}`}>
              <Icon name={active ? "check" : "warning"} size={20} />
            </span>
            <div>
              <p className="eyebrow">Current state</p>
              <h2>
                {active ? "Authorized for testing" : expired ? "Authorization expired" : "Authorization required"}
              </h2>
              <p>
                {active
                  ? "MarketTwin may create tests against this target while authorization remains active."
                  : expired
                    ? "This authorization has expired. An owner or admin must confirm permission again before MarketTwin can create a test."
                    : "An owner or admin must explicitly confirm permission before MarketTwin can create a test."}
              </p>
            </div>
          </div>
          {active && authorization ? (
            <div className="audit-box">
              <div>
                <span>Authorized</span>
                <strong>
                  {authorization.authorized_at
                    ? new Date(authorization.authorized_at).toLocaleString()
                    : "Active"}
                </strong>
              </div>
              <div>
                <span>Basis</span>
                <strong>{authorization.authorization_basis}</strong>
              </div>
              {authorization.expires_at ? (
                <div>
                  <span>Expires</span>
                  <strong>
                    {new Date(authorization.expires_at).toLocaleString()}
                  </strong>
                </div>
              ) : null}
            </div>
          ) : null}
          <div className="audit-box">
            <h3>Exact execution scope under review</h3>
            <ul>{target.allowed_origins.map((origin) => <li key={`${origin.scheme}:${origin.hostname}:${origin.port}`}>
              <code>{origin.scheme}://{origin.hostname.includes(":") ? `[${origin.hostname}]` : origin.hostname}{origin.port ? `:${origin.port}` : ""}</code>
              {origin.include_subdomains ? " (includes subdomains)" : " (exact origin)"}
            </li>)}</ul>
            <p>Approval applies to this target only. Existing runs keep their frozen scope.</p>
            {authorization?.status === "pending" ? <p>Requested reason: {authorization.authorization_basis}</p> : null}
          </div>
          {!active && mayAuthorize ? (
            <form className="form-grid authorization-form" onSubmit={authorize}>
              <label className="field-label" htmlFor="basis">
                Why are you authorized to test this target?
              </label>
              <textarea
                id="basis"
                className="text-area"
                rows={5}
                value={basis}
                onChange={(event) => {
                  setBasis(event.target.value);
                  setError(null);
                }}
                placeholder="For example: This staging environment is owned and operated by our team for internal product testing."
                minLength={10}
                maxLength={2000}
                required
              />
              <label className="confirmation-row">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                <span>
                  I confirm that I own or have permission to test every origin
                  listed in this execution scope.
                </span>
              </label>
              {error ? (
                <p className="form-error" role="alert">
                  {error}
                </p>
              ) : null}
              <button
                className="primary-button align-start"
                type="submit"
                disabled={busy || basis.trim().length < 10 || !confirmed}
              >
                {busy ? (
                  <>
                    <Spinner /> Authorizing
                  </>
                ) : (
                  "Authorize target"
                )}
              </button>
            </form>
          ) : null}
          {!active && !mayAuthorize ? (
            <div className="inline-note">
              Your {workspace.role} role can view authorization state but cannot
              authorize this target. Ask a workspace owner or admin.
            </div>
          ) : null}
          {active && mayAuthorize ? (
            <div className="revoke-row">
              <div>
                <strong>Revoke authorization</strong>
                <p>
                  Blocks creation of new tests against this target. Historical
                  authorization remains auditable.
                </p>
              </div>
              <button
                className="danger-button"
                type="button"
                onClick={() => void revoke()}
                disabled={busy}
              >
                Revoke
              </button>
            </div>
          ) : null}
          {error && active ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
        </section>
        <aside className="info-card">
          <span className="info-icon">
            <Icon name="shield" size={18} />
          </span>
          <h2>Authorization is live state</h2>
          <p>
            A past authorization ID is retained for audit, but the backend
            rechecks current authorization before creating a Test Run.
          </p>
        </aside>
      </div>
    </>
  );
}

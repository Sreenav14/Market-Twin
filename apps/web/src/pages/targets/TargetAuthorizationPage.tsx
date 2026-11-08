import { FormEvent, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import {
  ErrorPanel,
  LoadingPanel,
  Spinner,
} from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { ErrorSummary, FieldError, RequiredLegend, RequiredMark } from "../../components/ui/Field";
import { InlineAlert } from "../../components/ui/Feedback";
import { ApiError, TargetAuthorization, api } from "../../lib/api";
import { canAuthorizeTarget } from "../../lib/permissions";
import { isAuthorizationActive } from "../../lib/targetAuthorization";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

function originLabel(origin: {
  scheme: string;
  hostname: string;
  port: number | null;
}) {
  const host = origin.hostname.includes(":")
    ? `[${origin.hostname}]`
    : origin.hostname;
  return `${origin.scheme}://${host}${origin.port ? `:${origin.port}` : ""}`;
}

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
  const [authSubmitted, setAuthSubmitted] = useState(false);
  const basisError = authSubmitted && basis.trim().length < 10
    ? "Enter the reason you are authorized to test this target, in at least 10 characters."
    : null;
  const confirmError = authSubmitted && !confirmed
    ? "Confirm that you are authorized to test every destination in this scope."
    : null;
  const authSummaryErrors = [
    ...(basisError ? [{ targetId: "basis", message: basisError }] : []),
    ...(confirmError ? [{ targetId: "attest-confirm", message: confirmError }] : []),
  ];
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (
    targetState.status === "loading" ||
    authorizationState.status === "loading"
  )
    return <LoadingPanel label="Loading authorization security document" />;
  if (targetState.status === "error")
    return <ErrorPanel message={targetState.error} />;
  if (authorizationState.status === "error")
    return <ErrorPanel message={authorizationState.error} />;

  const target = targetState.data;
  const authorization = authorizationState.data;
  const active = isAuthorizationActive(authorization);
  const expired = authorization?.status === "authorized" && !active;
  const revoked = authorization?.status === "revoked";
  const mayAuthorize =
    canAuthorizeTarget(workspace.role) && target.status === "active";

  async function authorize(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthSubmitted(true);
    if (basis.trim().length < 10 || !confirmed || busy) return;

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
    if (!confirmRevoke || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.revokeAuthorization(targetId);
      setConfirmRevoke(false);
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
        eyebrow="Target security approval"
        title={`Authorization: ${target.name}`}
        description={`${target.environment.toUpperCase()} · ${target.base_url}`}
        action={
          <Link className="secondary-button" to={`/targets/${target.id}`}>
            Target overview
          </Link>
        }
      />

      <div className="tab-strip" aria-label="Target sections">
        <Link
          className="tab-link"
          to={`/targets/${target.id}`}
        >
          Scope receipt
        </Link>
        <span className="tab-link active">Authorization</span>
        <Link
          className="tab-link"
          to={`/targets/${target.id}/network`}
        >
          Network policy
        </Link>
        <Link
          className="tab-link"
          to={`/applications/${target.application_id}`}
        >
          Application
        </Link>
      </div>

      <div className="two-column-layout">
        <div style={{ display: "grid", gap: "24px" }}>
          {/* Section 1: Currently Authorized Scope */}
          <section className="panel" aria-labelledby="current-scope-heading">
            <div className="section-heading compact-heading">
              <div>
                <p className="eyebrow">Active permission state</p>
                <h2 id="current-scope-heading">Currently authorized scope</h2>
              </div>
              <StatusBadge
                status={
                  active
                    ? "authorized"
                    : revoked
                      ? "revoked"
                      : expired
                        ? "expired"
                        : authorization?.status === "pending"
                          ? "pending"
                          : "not authorized"
                }
              />
            </div>

            {active && authorization ? (
              <div>
                <p style={{ color: "var(--text-2)", margin: "0 0 16px", lineHeight: "1.6" }}>
                  MarketTwin browser testers are authorized to execute tests against the approved destinations below.
                </p>
                <dl className="definition-list">
                  <div>
                    <dt>Authorized on</dt>
                    <dd>
                      {authorization.authorized_at
                        ? new Date(authorization.authorized_at).toLocaleString()
                        : "Active"}
                    </dd>
                  </div>
                  <div>
                    <dt>Recorded basis</dt>
                    <dd style={{ fontStyle: "italic" }}>
                      &ldquo;{authorization.authorization_basis}&rdquo;
                    </dd>
                  </div>
                  <div>
                    <dt>Authorized by</dt>
                    <dd>
                      {authorization.authorized_by_user_id
                        ? "Workspace Administrator"
                        : "Owner attestation"}
                    </dd>
                  </div>
                  <div>
                    <dt>Expiration</dt>
                    <dd>
                      {authorization.expires_at
                        ? new Date(authorization.expires_at).toLocaleString()
                        : "Continuous until explicitly revoked"}
                    </dd>
                  </div>
                </dl>
              </div>
            ) : expired ? (
              <InlineAlert severity="error" title="Authorization has expired">The previous authorization for this target expired on {authorization?.expires_at ? new Date(authorization.expires_at).toLocaleString() : "an earlier date"}. Test execution is blocked until an Owner or Admin re-authorizes.</InlineAlert>
            ) : revoked ? (
              <InlineAlert severity="error" title="Authorization was revoked">Authorization was revoked on {authorization?.revoked_at ? new Date(authorization.revoked_at).toLocaleString() : "record"}. Running tests cannot execute against this target.</InlineAlert>
            ) : (
              <div className="panel-note" style={{ margin: "8px 0 0" }}>
                No active authorization is on record for this target. Browser testers are strictly blocked from dispatching requests to this target.
              </div>
            )}
          </section>

          {/* Section 2: Requested Execution Scope */}
          <section className="panel" aria-labelledby="requested-scope-heading">
            <div className="section-heading compact-heading">
              <div>
                <p className="eyebrow">Security boundary</p>
                <h2 id="requested-scope-heading">Requested execution scope</h2>
              </div>
            </div>

            <p style={{ color: "var(--text-2)", margin: "0 0 14px", fontSize: "14px", lineHeight: "1.6" }}>
              Browser testers will be strictly confined to these exact destinations.
            </p>

            <div className="origin-list">
              {target.allowed_origins.map((origin) => (
                <div key={originLabel(origin)}>
                  <code>{originLabel(origin)}</code>
                  <span style={{ fontSize: "11px", color: "var(--text-3)" }}>
                    {origin.include_subdomains
                      ? "Includes subdomains (legacy permission)"
                      : "Exact origin (subdomains blocked)"}
                  </span>
                </div>
              ))}
            </div>

            <div className="panel-note" style={{ marginTop: "14px" }}>
              <strong>Subdomains are not implicitly allowed:</strong> If tests must access auxiliary hostnames (e.g. <code>api.example.com</code> or <code>cdn.example.com</code>), each origin must be explicitly requested and approved via Target Network Policy.
            </div>
          </section>

          {/* Section 3: Approval / Attestation Form */}
          {!active && mayAuthorize ? (
            <section className="panel" aria-labelledby="attest-heading">
              <div className="section-heading compact-heading">
                <div>
                  <p className="eyebrow">Approval action</p>
                  <h2 id="attest-heading">Attest &amp; authorize testing</h2>
                </div>
              </div>

              <form className="form-grid" onSubmit={authorize} noValidate>
                {authSubmitted && authSummaryErrors.length ? <ErrorSummary errors={authSummaryErrors} /> : null}
                <RequiredLegend />
                <div>
                  <label className="field-label" htmlFor="basis">
                    Why are you authorized to test this target? <RequiredMark required />
                  </label>
                  <textarea
                    id="basis"
                    className="text-area"
                    rows={4}
                    value={basis}
                    onChange={(event) => {
                      setBasis(event.target.value);
                      setError(null);
                    }}
                    placeholder="For example: This staging environment is operated by our team for pre-release quality assurance and automated workflow testing."
                    minLength={10}
                    maxLength={2000}
                    required
                    aria-invalid={basisError ? true : undefined}
                    aria-describedby={basisError ? "basis-help basis-error" : "basis-help"}
                  />
                  <p className="form-help" id="basis-help">
                    Minimum 10 characters required for audit compliance.
                  </p>
                  {basisError ? <FieldError id="basis-error">{basisError}</FieldError> : null}
                </div>

                <div>
                <label className="confirmation-row">
                  <input
                    id="attest-confirm"
                    className="mt-checkbox"
                    type="checkbox"
                    checked={confirmed}
                    onChange={(event) => setConfirmed(event.target.checked)}
                    aria-invalid={confirmError ? true : undefined}
                    aria-describedby={confirmError ? "attest-confirm-error" : undefined}
                  />
                  <span>
                    <strong>I formally attest</strong> that I own, operate, or have explicit organizational permission to execute browser tests on every destination in this execution scope.
                  </span>
                </label>
                {confirmError ? <FieldError id="attest-confirm-error">{confirmError}</FieldError> : null}
                </div>

                {error ? (
                  <InlineAlert severity="error" title="Could not authorize target" role="alert">
                    {error}
                  </InlineAlert>
                ) : null}

                <div className="form-actions">
                  <button
                    className="primary-button"
                    type="submit"
                    disabled={busy}
                  >
                    {busy ? (
                      <>
                        <Spinner /> Authorizing scope…
                      </>
                    ) : (
                      "Authorize target for testing"
                    )}
                  </button>
                </div>
              </form>
            </section>
          ) : null}

          {/* Viewer role notification */}
          {!active && !mayAuthorize ? (
            <div className="panel" style={{ background: "var(--surface-muted)" }}>
              <p style={{ margin: 0, color: "var(--text-2)", fontSize: "13px" }}>
                Your role ({workspace.role}) has read-only access to authorization policies. Authorizing or revoking execution scopes requires Workspace Owner or Admin privileges.
              </p>
            </div>
          ) : null}

          {/* Section 4: Revocation Safeguard */}
          {active && mayAuthorize ? (
            <section
              className="panel"
              style={{ borderColor: "var(--danger-border, var(--border))" }}
              aria-labelledby="revoke-heading"
            >
              <div className="section-heading compact-heading">
                <div>
                  <p className="eyebrow" style={{ color: "var(--danger)" }}>
                    Security control
                  </p>
                  <h2 id="revoke-heading">Revoke authorization</h2>
                </div>
              </div>

              <p style={{ color: "var(--text-2)", fontSize: "13px", lineHeight: "1.6", margin: "0 0 14px" }}>
                Revoking authorization immediately prohibits any new tests against this target and halts execution. Historical test reports and evidence remain permanently auditable.
              </p>

              <label className="confirmation-row" style={{ marginBottom: "14px" }}>
                <input
                  type="checkbox"
                  className="mt-checkbox"
                  checked={confirmRevoke}
                  onChange={(e) => setConfirmRevoke(e.target.checked)}
                />
                <span>
                  I understand that revoking authorization will immediately block tests on this target.
                </span>
              </label>

              {error ? (
                <InlineAlert severity="error" title="Could not revoke authorization" role="alert">
                  {error}
                </InlineAlert>
              ) : null}

              <button
                className="danger-button"
                type="button"
                onClick={() => void revoke()}
                disabled={busy || !confirmRevoke}
              >
                {busy ? (
                  <>
                    <Spinner /> Revoking…
                  </>
                ) : (
                  "Confirm & revoke authorization"
                )}
              </button>
            </section>
          ) : null}
        </div>

        {/* Sidebar / Governance Explanation */}
        <aside className="info-card">
          <span className="info-icon">
            <Icon name="shield" size={20} />
          </span>
          <h2>Live authorization checks</h2>
          <p>
            MarketTwin enforces target authorization at runtime. Before any browser task dispatches, the control plane re-verifies that target authorization remains active and unexpired.
          </p>
          <p style={{ marginTop: "12px" }}>
            <strong>Audit compliance:</strong> Every authorization grant and revocation records the attesting administrator ID, timestamp, and business justification.
          </p>
          <p style={{ marginTop: "12px" }}>
            <strong>Scope immutability:</strong> Modifying allowed origins requires creating a new scope revision so that past tests remain permanently linked to their exact original security boundary.
          </p>
        </aside>
      </div>
    </>
  );
}

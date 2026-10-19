import { FormEvent, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";
import { PageHeader } from "../../components/ui/PageHeader";
import { ErrorPanel, LoadingPanel, Spinner } from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { AllowedOrigin, api } from "../../lib/api";
import { canAuthorizeTarget } from "../../lib/permissions";
import { useAsync } from "../../lib/useAsync";
import { AppShellContext } from "../../layouts/AppShell";

function originLabel(origin: { scheme: string; hostname: string; port: number | null }) {
  const host = origin.hostname.includes(":") ? `[${origin.hostname}]` : origin.hostname;
  return `${origin.scheme}://${host}${origin.port ? `:${origin.port}` : ""}`;
}

export function TargetNetworkPolicyPage() {
  const { targetId = "" } = useParams();
  const { workspace } = useOutletContext<AppShellContext>();
  const [revision, setRevision] = useState(0);

  const state = useAsync(
    async () => ({
      target: await api.getTarget(targetId),
      revisions: await api.listScopeRevisions(targetId),
    }),
    [targetId, revision],
  );

  const [name, setName] = useState("");
  const [origins, setOrigins] = useState("");
  const [basis, setBasis] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (state.status === "loading")
    return <LoadingPanel label="Loading execution scopes & network policy" />;
  if (state.status === "error")
    return <ErrorPanel message={state.error} />;

  const { target, revisions } = state.data;
  const mayRequest = canAuthorizeTarget(workspace.role);

  const currentOriginLabels = new Set(target.allowed_origins.map(originLabel));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const originList = origins
      .split(/\r?\n/)
      .map((value) => value.trim())
      .filter(Boolean);

    if (!name.trim() || originList.length === 0 || basis.trim().length < 10 || !confirmed) {
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await api.requestScopeRevision(targetId, {
        name: name.trim(),
        origins: originList,
        request_basis: basis.trim(),
      });
      setRevision((value) => value + 1);
      setName("");
      setOrigins("");
      setBasis("");
      setConfirmed(false);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Could not request scope revision.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Target network policy"
        title={`Execution scopes: ${target.name}`}
        description="Destinations outside approved scope require an exact origin definition and separate owner or admin authorization."
        action={
          <Link className="secondary-button" to={`/targets/${target.id}`}>
            Target overview
          </Link>
        }
      />

      <div className="tab-strip" aria-label="Target sections">
        <Link className="tab-link" to={`/targets/${target.id}`}>
          Scope receipt
        </Link>
        <Link className="tab-link" to={`/targets/${target.id}/authorization`}>
          Authorization
        </Link>
        <span className="tab-link active">Network policy</span>
        <Link className="tab-link" to={`/applications/${target.application_id}`}>
          Application
        </Link>
      </div>

      <div style={{ display: "grid", gap: "24px" }}>
        {/* Current Approved Scope Panel */}
        <section className="panel" aria-labelledby="current-policy-heading">
          <div className="section-heading compact-heading">
            <div>
              <p className="eyebrow">Approved boundary</p>
              <h2 id="current-policy-heading">Current scope: {target.name}</h2>
            </div>
            <StatusBadge status={target.status} />
          </div>

          <p style={{ color: "var(--text-2)", fontSize: "14px", lineHeight: "1.6", margin: "0 0 14px" }}>
            Test agents executing against this target are permitted to communicate with only these exact origins:
          </p>

          <div className="origin-list">
            {target.allowed_origins.map((origin) => (
              <div key={originLabel(origin)}>
                <code>{originLabel(origin)}</code>
                <span style={{ fontSize: "11px", color: "var(--text-3)" }}>
                  {origin.include_subdomains
                    ? "Includes subdomains (legacy)"
                    : "Exact origin (subdomains blocked)"}
                </span>
              </div>
            ))}
          </div>

          <div className="panel-note" style={{ marginTop: "14px" }}>
            Existing tests preserve their frozen snapshot. A new scope creates a separate target; it cannot execute tests until explicitly authorized.
          </div>

          {target.scope_parent_id ? (
            <div style={{ marginTop: "12px" }}>
              <Link
                to={`/targets/${target.scope_parent_id}/network`}
                className="text-link"
                style={{ fontSize: "12px" }}
              >
                &larr; View original parent execution scope
              </Link>
            </div>
          ) : null}
        </section>

        {/* Requested Scope Revisions with Origin Diff */}
        <section className="panel" aria-labelledby="revisions-heading">
          <div className="section-heading compact-heading">
            <div>
              <p className="eyebrow">Scope history &amp; diffs</p>
              <h2 id="revisions-heading">Requested scope revisions</h2>
            </div>
          </div>

          {revisions.length === 0 ? (
            <p style={{ color: "var(--text-3)", margin: "8px 0 0", fontSize: "14px" }}>
              No revisions requested for this target. The current scope remains active.
            </p>
          ) : (
            <div style={{ display: "grid", gap: "16px", marginTop: "12px" }}>
              {revisions.map((rev) => {
                const revOriginLabels = new Set(rev.allowed_origins.map(originLabel));

                const added: AllowedOrigin[] = rev.allowed_origins.filter(
                  (o) => !currentOriginLabels.has(originLabel(o)),
                );
                const removed: AllowedOrigin[] = target.allowed_origins.filter(
                  (o) => !revOriginLabels.has(originLabel(o)),
                );
                const retained: AllowedOrigin[] = rev.allowed_origins.filter(
                  (o) => currentOriginLabels.has(originLabel(o)),
                );

                return (
                  <div
                    key={rev.id}
                    style={{
                      border: "1px solid var(--border)",
                      borderRadius: "8px",
                      padding: "16px",
                      background: "var(--surface)",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        flexWrap: "wrap",
                        gap: "8px",
                        marginBottom: "12px",
                      }}
                    >
                      <strong style={{ fontSize: "15px" }}>{rev.name}</strong>
                      <span
                        className="status-badge status-warning"
                        style={{ fontSize: "11px" }}
                      >
                        Pending — does not grant test execution permission
                      </span>
                    </div>

                    <div style={{ display: "grid", gap: "8px", margin: "12px 0" }}>
                      {added.map((o) => (
                        <div
                          key={`added-${originLabel(o)}`}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            padding: "6px 10px",
                            borderRadius: "6px",
                            background: "var(--success-bg)",
                            border: "1px solid var(--success-border)",
                            color: "var(--success)",
                            fontSize: "13px",
                          }}
                        >
                          <code>+ {originLabel(o)}</code>
                          <span style={{ fontSize: "11px" }}>Newly requested addition</span>
                        </div>
                      ))}

                      {removed.map((o) => (
                        <div
                          key={`removed-${originLabel(o)}`}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            padding: "6px 10px",
                            borderRadius: "6px",
                            background: "var(--danger-bg)",
                            border: "1px solid var(--danger-border)",
                            color: "var(--danger)",
                            fontSize: "13px",
                          }}
                        >
                          <code>- {originLabel(o)}</code>
                          <span style={{ fontSize: "11px" }}>Removed from scope</span>
                        </div>
                      ))}

                      {retained.map((o) => (
                        <div
                          key={`retained-${originLabel(o)}`}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            padding: "6px 10px",
                            borderRadius: "6px",
                            background: "var(--surface-muted)",
                            border: "1px solid var(--border)",
                            color: "var(--text-2)",
                            fontSize: "13px",
                          }}
                        >
                          <code>= {originLabel(o)}</code>
                          <span style={{ fontSize: "11px", color: "var(--text-3)" }}>
                            Retained unchanged
                          </span>
                        </div>
                      ))}
                    </div>

                    <div style={{ marginTop: "14px" }}>
                      <Link
                        to={`/targets/${rev.id}/authorization`}
                        className="secondary-button compact"
                      >
                        <Icon name="shield" size={14} /> Review authorization status and scope
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Request New Scope Form */}
        <section className="panel" aria-labelledby="request-scope-heading">
          <div className="section-heading compact-heading">
            <div>
              <p className="eyebrow">Modify perimeter</p>
              <h2 id="request-scope-heading">Request a new execution scope</h2>
            </div>
          </div>

          {mayRequest ? (
            <form className="form-grid" onSubmit={submit} noValidate>
              <div>
                <label className="field-label" htmlFor="scope-name">
                  New target name
                </label>
                <input
                  className="text-input"
                  id="scope-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. Staging with Payment Gateway Scope"
                  required
                  maxLength={200}
                />
              </div>

              <div>
                <label className="field-label" htmlFor="scope-origins">
                  Complete exact-origin scope, one per line
                </label>
                <textarea
                  className="text-area monospace"
                  id="scope-origins"
                  value={origins}
                  onChange={(event) => setOrigins(event.target.value)}
                  rows={5}
                  required
                  placeholder={target.allowed_origins.map(originLabel).join("\n")}
                />
                <p className="panel-note" style={{ marginTop: "4px" }}>
                  Include the base origin and each approved application, API, or SSO origin. Paths, wildcards, and automatic subdomain trust are not supported.
                </p>
              </div>

              <div>
                <label className="field-label" htmlFor="scope-basis">
                  Reason for this requested scope
                </label>
                <textarea
                  className="text-area"
                  id="scope-basis"
                  value={basis}
                  onChange={(event) => setBasis(event.target.value)}
                  rows={3}
                  minLength={10}
                  maxLength={2000}
                  placeholder="Explain why these origins are needed (e.g. Checkout flow redirects through auth.example.com)."
                  required
                />
                <small style={{ color: "var(--text-3)", fontSize: "11px" }}>
                  Minimum 10 characters required.
                </small>
              </div>

              <label className="confirmation-row">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                <span>
                  <strong>I understand</strong> this creates a pending target and does not grant test execution permission until explicitly authorized.
                </span>
              </label>

              {error ? (
                <p role="alert" className="form-error">
                  {error}
                </p>
              ) : null}

              <div className="form-actions">
                <button
                  className="primary-button"
                  type="submit"
                  disabled={
                    busy ||
                    !confirmed ||
                    basis.trim().length < 10 ||
                    !name.trim() ||
                    !origins.trim()
                  }
                >
                  {busy ? (
                    <>
                      <Spinner /> Creating scope request…
                    </>
                  ) : (
                    "Create pending scope"
                  )}
                </button>
              </div>
            </form>
          ) : (
            <div className="panel-note">
              Only workspace owners and admins can request or authorize new execution scopes. Contact an administrator to expand testing boundaries.
            </div>
          )}
        </section>
      </div>
    </>
  );
}

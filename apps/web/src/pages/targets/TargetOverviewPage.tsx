import { Link, useOutletContext, useParams } from "react-router-dom";
import { Icon } from "../../components/ui/Icon";
import { LifecyclePanel } from "../../components/ui/LifecyclePanel";
import { PageHeader } from "../../components/ui/PageHeader";
import { ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { ApiError, TargetAuthorization, api } from "../../lib/api";
import {
  canAuthorizeTarget,
  canManageLifecycle,
  canWriteWorkspace,
} from "../../lib/permissions";
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

export function TargetOverviewPage() {
  const { targetId = "" } = useParams();
  const { workspace } = useOutletContext<AppShellContext>();

  const targetState = useAsync(() => api.getTarget(targetId), [targetId]);
  const authorizationState = useAsync<TargetAuthorization | null>(async () => {
    try {
      return await api.getAuthorization(targetId);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  }, [targetId]);

  if (
    targetState.status === "loading" ||
    authorizationState.status === "loading"
  )
    return <LoadingPanel label="Loading target" />;
  if (targetState.status === "error")
    return <ErrorPanel message={targetState.error} />;
  if (authorizationState.status === "error")
    return <ErrorPanel message={authorizationState.error} />;

  const target = targetState.data;
  const authorization = authorizationState.data;
  const authorized = isAuthorizationActive(authorization);
  const expired = authorization?.status === "authorized" && !authorized;
  const revoked = authorization?.status === "revoked";
  const pending = authorization?.status === "pending";

  const authBadgeStatus = authorized
    ? "authorized"
    : revoked
      ? "revoked"
      : expired
        ? "expired"
        : pending
          ? "pending"
          : "not authorized";

  const canWrite =
    canWriteWorkspace(workspace.role) && target.status === "active";
  const canAuthorize = canAuthorizeTarget(workspace.role);

  let baseOrigin = target.base_url;
  try {
    baseOrigin = new URL(target.base_url).origin;
  } catch {
    // fallback
  }

  return (
    <>
      <PageHeader
        eyebrow="Target environment"
        title={target.name}
        description={`${target.environment.toUpperCase()} · ${target.base_url}`}
        action={
          authorized && canWrite ? (
            <Link
              className="primary-button"
              to={`/applications/${target.application_id}/runs/new`}
            >
              <Icon name="plus" size={16} /> New test
            </Link>
          ) : !authorized && canAuthorize ? (
            <Link
              className="primary-button"
              to={`/targets/${target.id}/authorization`}
            >
              <Icon name="shield" size={16} /> Authorize target
            </Link>
          ) : (
            <Link
              className="secondary-button"
              to={`/targets/${target.id}/authorization`}
            >
              <Icon name="shield" size={16} /> View authorization
            </Link>
          )
        }
      />

      <div className="tab-strip" aria-label="Target sections">
        <span className="tab-link active">Scope receipt</span>
        <Link
          className="tab-link"
          to={`/targets/${target.id}/authorization`}
        >
          Authorization
        </Link>
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

      <div className="detail-grid">
        {/* Scope Receipt Panel */}
        <section className="panel" aria-labelledby="scope-receipt-heading">
          <div className="section-heading compact-heading">
            <div>
              <p className="eyebrow">Verification receipt</p>
              <h2 id="scope-receipt-heading">Scope Receipt</h2>
            </div>
            <StatusBadge status={authBadgeStatus} />
          </div>

          <dl className="definition-list">
            <div>
              <dt>Target origin</dt>
              <dd className="monospace">{baseOrigin}</dd>
            </div>
            <div>
              <dt>Environment</dt>
              <dd style={{ textTransform: "capitalize" }}>{target.environment}</dd>
            </div>
            <div>
              <dt>Lifecycle status</dt>
              <dd>
                <StatusBadge status={target.status} />
              </dd>
            </div>
            <div>
              <dt>Authorization status</dt>
              <dd>
                <StatusBadge status={authBadgeStatus} />
              </dd>
            </div>
            <div>
              <dt>Authentication</dt>
              <dd>
                {target.requires_auth
                  ? "Protected (login assistance enabled)"
                  : "Public (no authentication)"}
              </dd>
            </div>
            {authorization?.authorization_basis ? (
              <div>
                <dt>Permission basis</dt>
                <dd style={{ fontStyle: "italic" }}>
                  &ldquo;{authorization.authorization_basis}&rdquo;
                </dd>
              </div>
            ) : null}
            {authorization?.authorized_at ? (
              <div>
                <dt>Authorized at</dt>
                <dd>{new Date(authorization.authorized_at).toLocaleString()}</dd>
              </div>
            ) : null}
            <div>
              <dt>Expiry</dt>
              <dd>
                {authorization?.expires_at
                  ? new Date(authorization.expires_at).toLocaleString()
                  : authorized
                    ? "Continuous (active until revoked)"
                    : "No active authorization"}
              </dd>
            </div>
            <div>
              <dt>Full base URL</dt>
              <dd className="monospace">{target.base_url}</dd>
            </div>
          </dl>

          <div style={{ marginTop: "20px", display: "flex", gap: "10px", flexWrap: "wrap" }}>
            {authorized && canWrite ? (
              <Link
                to={`/applications/${target.application_id}/runs/new`}
                className="primary-button"
              >
                <Icon name="plus" size={16} /> New test against target
              </Link>
            ) : !authorized && canAuthorize ? (
              <Link
                to={`/targets/${target.id}/authorization`}
                className="primary-button"
              >
                <Icon name="shield" size={16} /> Authorize this target
              </Link>
            ) : (
              <p className="panel-note" style={{ margin: 0 }}>
                Authorization required before tests can execute.
              </p>
            )}
            <Link
              to={`/targets/${target.id}/network`}
              className="secondary-button"
            >
              Manage network scope
            </Link>
          </div>
        </section>

        {/* Network & Allowed Origins Panel */}
        <section className="panel" aria-labelledby="allowed-origins-heading">
          <div className="section-heading compact-heading">
            <div>
              <p className="eyebrow">Network boundary</p>
              <h2 id="allowed-origins-heading">Allowed execution origins</h2>
            </div>
            <Link
              to={`/targets/${target.id}/network`}
              className="text-link"
              style={{ fontSize: "12px" }}
            >
              Request revisions
            </Link>
          </div>

          <div className="origin-list">
            {target.allowed_origins.map((origin) => (
              <div key={originLabel(origin)}>
                <code>{originLabel(origin)}</code>
                <span style={{ fontSize: "11px", color: "var(--text-3)" }}>
                  {origin.include_subdomains
                    ? "Includes subdomains (legacy)"
                    : "Exact host only"}
                </span>
              </div>
            ))}
          </div>

          <div style={{ marginTop: "18px" }}>
            <p className="field-label" style={{ marginBottom: "6px" }}>
              Auth-only origins
            </p>
            <p className="panel-note" style={{ margin: 0 }}>
              None configured. External identity providers or SSO redirection origins must be explicitly approved in network policy.
            </p>
          </div>

          <p className="panel-note" style={{ marginTop: "14px" }}>
            Subdomains are not implicitly trusted. Test agents will fail with a policy block if navigation leaves these exact origins.
          </p>
        </section>
      </div>

      {canManageLifecycle(workspace.role) ? (
        <LifecyclePanel
          entityType="target"
          entityName={target.name}
          entityId={target.id}
          returnTo={`/applications/${target.application_id}/targets`}
        />
      ) : null}
    </>
  );
}

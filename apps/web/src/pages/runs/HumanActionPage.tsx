import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Clock3, ShieldCheck, UserRound } from "lucide-react";
import { Link, useLocation, useOutletContext } from "react-router-dom";

import type { RunContext } from "../../layouts/RunLayout";
import { api, type HumanAction, type HumanLeaseGrant, type LiveExecution } from "../../lib/api";
import { canAuthorizeTarget } from "../../lib/permissions";
import { terminalTestStatuses } from "../../lib/results";
import { HumanBrowserViewer } from "./HumanBrowserViewer";

function RequestContext({ action, runId }: { action: HumanAction; runId: string }) {
  return <div className="muted">
    <p>Requesting executor: {action.requesting_agent ?? "Browser executor"} · {action.journey_title ?? `Execution ${action.execution_id.slice(0, 8)}`}</p>
    {action.journey_id ? <Link className="text-link" to={`/runs/${runId}/journeys/${action.journey_id}${action.requested_by_step_id ? `?step=${action.requested_by_step_id}` : ""}`}>Inspect the paused journey{action.requested_by_step_id ? ` at step ${action.requested_by_step_id}` : ""}</Link> : null}
  </div>;
}

const HumanAssistanceContainer = createContext<HTMLDivElement | null>(null);
type ActiveControl = { requestId: string; done: () => void } | null;

/** One lease/viewer owner persists across run routes; the portal target never changes. */
export function HumanAssistanceHost({ context, children }: { context: RunContext; children: ReactNode }) {
  const [container] = useState(() => document.createElement("div"));
  const [control, setControl] = useState<ActiveControl>(null);
  const fallback = useRef<HTMLDivElement>(null);
  const location = useLocation();
  const inline = location.pathname.endsWith("/activity");
  const showing = inline || location.pathname.endsWith("/human-action");
  useLayoutEffect(() => {
    if (!showing && !container.parentElement) fallback.current?.append(container);
  }, [showing, container]);
  return <HumanAssistanceContainer.Provider value={container}>
    {control && !showing ? <section className="run-action-required" role="status">
      <div><h2>You still control the test browser</h2><p>The agent is paused. Return to the browser or finish the handoff.</p></div>
      <Link className="secondary-button" to={`/runs/${context.run.id}/activity`}>Return to browser control</Link>
      <button type="button" className="primary-button" onClick={control.done}>Done—resume agent</button>
    </section> : null}
    {children}
    <div ref={fallback} hidden={showing || !control} className="human-assistance-fallback" />
    {createPortal(<HumanActionPanel context={context} inline={inline} onControlChange={setControl} />, container)}
  </HumanAssistanceContainer.Provider>;
}

export function HumanActionPage() {
  const container = useContext(HumanAssistanceContainer);
  const slot = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!container || !slot.current) return;
    slot.current.append(container);
    return () => { container.remove(); };
  }, [container]);
  return container ? <div ref={slot} className="human-assistance-slot" /> : <HumanActionPanel />;
}

function HumanActionPanel({ context, inline = false, onControlChange }: {
  context?: RunContext; inline?: boolean; onControlChange?: (control: ActiveControl) => void;
}) {
  const inherited = useOutletContext<RunContext>();
  const { run, user, workspace } = context ?? inherited;
  const canManageHumanActions = canAuthorizeTarget(workspace.role);
  const ended = terminalTestStatuses.has(run.status);
  const authorityRef = useRef(false);
  authorityRef.current = canManageHumanActions && !ended;
  const actions = useQuery({
    queryKey: ["human-actions", user.id, workspace.id, run.id],
    queryFn: ({ signal }) => api.listHumanActions(run.id, signal),
    enabled: canManageHumanActions,
    refetchInterval: canManageHumanActions ? 2500 : false,
  });
  const queryClient = useQueryClient();
  const pauseStatus = useSyncExternalStore(
    (notify) => queryClient.getQueryCache().subscribe(notify),
    () => queryClient.getQueryData<LiveExecution>(["live-execution", user.id, workspace.id, workspace.role, run.id])?.pause?.status ?? "",
  );
  const resumePending = ["resume_requested", "verifying"].includes(pauseStatus);
  const [activeLease, setActiveLease] = useState<HumanLeaseGrant | null>(null);
  const activeLeaseRef = useRef<HumanLeaseGrant | null>(null);
  const mountedRef = useRef(true);
  const [activeRequestId, setActiveRequestId] = useState<string | null>(null);
  const [decisionMessage, setDecisionMessage] = useState<string | null>(null);
  const releasingRef = useRef(false);
  const claim = useMutation({
    mutationFn: async (requestId: string) => {
      const lease = await api.claimHumanAction(requestId);
      if (!mountedRef.current || !authorityRef.current) return;
      activeLeaseRef.current = lease;
      setActiveLease(lease);
      setActiveRequestId(requestId);
    },
    onSuccess: (_result, requestId) => {
      releasingRef.current = false;
      queryClient.invalidateQueries({ queryKey: ["human-actions", user.id, workspace.id, run.id] });
    },
  });
  const renew = useMutation({
    mutationFn: (requestId: string) => {
      const lease = activeLeaseRef.current;
      if (!lease) throw new Error("The local browser lease is no longer available.");
      return api.renewHumanAction(requestId, lease);
    },
    onSuccess: ({ expires_at }) => {
      const lease = activeLeaseRef.current;
      if (lease) {
        const renewed = { ...lease, expires_at };
        activeLeaseRef.current = renewed;
        setActiveLease(renewed);
      }
    },
    onError: () => {
      if (releasingRef.current) return;
      setActiveLease(null);
      setActiveRequestId(null);
      activeLeaseRef.current = null;
      queryClient.invalidateQueries({ queryKey: ["human-actions", user.id, workspace.id, run.id] });
    },
  });
  const release = useMutation({
    onMutate: () => { releasingRef.current = true; },
    mutationFn: (requestId: string) => {
      const lease = activeLeaseRef.current;
      if (!lease) throw new Error("The local browser lease is no longer available.");
      return api.releaseHumanAction(requestId, lease);
    },
    onSuccess: () => {
      releasingRef.current = false;
      activeLeaseRef.current = null;
      setActiveLease(null);
      setActiveRequestId(null);
      queryClient.invalidateQueries({ queryKey: ["human-actions", user.id, workspace.id, run.id] });
    },
  });
  const skip = useMutation({
    onMutate: () => { releasingRef.current = true; },
    mutationFn: async (requestId: string) => {
      await api.skipHumanAction(requestId);
    },
    onSuccess: (_result, requestId) => {
      releasingRef.current = false;
      if (activeRequestId === requestId) {
        activeLeaseRef.current = null;
        setActiveLease(null);
        setActiveRequestId(null);
      }
      queryClient.invalidateQueries({ queryKey: ["human-actions", user.id, workspace.id, run.id] });
    },
    onError: () => { releasingRef.current = false; },
  });
  const approvals = useQuery({
    queryKey: ["action-approvals", user.id, workspace.id, run.id],
    queryFn: ({ signal }) => api.listActionApprovals(run.id, signal),
    enabled: canManageHumanActions,
    refetchInterval: canManageHumanActions ? 2500 : false,
  });
  const decision = useMutation({
    mutationFn: ({ id, approved }: { id: string; approved: boolean }) =>
      api.decideActionApproval(id, approved),
    onSuccess: (_result, variables) => {
      setDecisionMessage(variables.approved ? "Approval recorded. The worker will validate and consume the one-time receipt." : "Approval rejected. The protected action remains blocked.");
      return queryClient.invalidateQueries({ queryKey: ["action-approvals", user.id, workspace.id, run.id] });
    },
  });
  const pending = actions.data?.filter((item) => item.status === "pending" && item.id !== activeRequestId) ?? [];
  const leased = actions.data?.filter((item) => item.status === "leased" && item.id !== activeRequestId) ?? [];
  const finished = actions.data?.filter((item) => ["completed", "cancelled", "expired", "skipped"].includes(item.status)) ?? [];
  const activeAction = actions.data?.find((item) => item.id === activeRequestId);
  const pendingApprovals = approvals.data?.filter((item) => item.status === "pending") ?? [];
  const approvedActions = approvals.data?.filter((item) => item.status === "approved") ?? [];

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      activeLeaseRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!activeLease || !activeRequestId || release.isPending || release.isError || skip.isPending) return;
    const timer = window.setInterval(() => {
      renew.mutate(activeRequestId);
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [activeLease, activeRequestId, release.isPending, release.isError, skip.isPending]);

  useEffect(() => {
    if (!canManageHumanActions || ended) {
      activeLeaseRef.current = null;
      setActiveLease(null);
      setActiveRequestId(null);
    }
  }, [canManageHumanActions, ended]);

  useEffect(() => {
    onControlChange?.(activeLease && activeRequestId && canManageHumanActions && !ended
      ? { requestId: activeRequestId, done: () => release.mutate(activeRequestId) } : null);
  }, [activeLease?.lease_id, activeRequestId, canManageHumanActions, ended, onControlChange]);

  if (inline && !activeLease && !pending.length && !leased.length && !pendingApprovals.length
      && !actions.isError && !approvals.isError && run.status !== "awaiting_human") return null;

  return (
    <section className="results-boundary" aria-labelledby="human-action-heading">
      <p className="section-label">Human assistance</p>
      <h2 id="human-action-heading">Continue in the test browser</h2>
      <p>MarketTwin pauses the agent while an authorized operator handles login, MFA, SSO, CAPTCHA, or another protected step.</p>
      {!canManageHumanActions ? <p className="human-action-denied" role="status">Human browser control and action approvals require an owner or administrator role. {run.status === "awaiting_human" ? "This test is paused until an authorized operator acts." : "Ask an authorized operator to review protected requests."}</p> : null}
      {canManageHumanActions ? <>
      <h2>Login and protected interaction</h2>
      <section className="human-action-group human-auth-group" aria-label="Login and protected interaction requests">

      {actions.isPending ? <p role="status">Checking for a human action request…</p> : null}
      {actions.isError ? <p role="alert">Human action status is unavailable. Retry this page in a moment.</p> : null}
      {actions.isSuccess && actions.data.length === 0 ? (
        <div className="empty-state">
          <Clock3 aria-hidden="true" />
          <h2>{ended ? "No human assistance was requested" : run.status === "awaiting_human" ? "Waiting for an available assistance request" : "No human assistance is needed right now"}</h2>
          <p>{ended ? "This test ended without a human handoff. There is no active takeover to connect to; review the recorded steps and evidence." : run.status === "awaiting_human" ? "The test reports a human wait, but no authorized request is available yet. Refresh the test if this state persists." : "Agents continue normally. A request and live browser controls appear here only when execution encounters a protected interaction."}</p>
          {ended ? <Link className="text-link" to={`/runs/${run.id}/journeys`}>Review execution and recorded evidence</Link> : null}
        </div>
      ) : null}

      {pending.map((action) => (
        <article className="study-summary" key={action.id}>
          <UserRound aria-hidden="true" />
          <div>
            <h2>Awaiting human: {action.request_type.replaceAll("_", " ")}</h2>
            <p>The agent is paused. Taking control opens the same supervised browser context.</p>
            <RequestContext action={action} runId={run.id} />
            {action.instructions ? <p>{action.instructions}</p> : null}
            {action.browser_state && action.browser_state !== "open" ? <p role="alert">This browser is no longer available for interaction. Review the request status or skip this work.</p> : null}
            <p className="muted">Request expires {action.expires_at ? new Date(action.expires_at).toLocaleString() : "when the run ends"}.</p>
          </div>
          <div className="button-row">
            <button className="secondary-button" type="button" disabled={claim.isPending || skip.isPending || Boolean(activeLease) || resumePending || Boolean(action.browser_state && action.browser_state !== "open")} onClick={() => claim.mutate(action.id)}>
              <ShieldCheck size={16} aria-hidden="true" /> Take browser control
            </button>
            <button className="secondary-button" type="button" disabled={skip.isPending || claim.isPending || release.isPending} onClick={() => skip.mutate(action.id)}>Skip this case/journey</button>
          </div>
        </article>
      ))}

      {claim.isError ? <p role="alert">Browser control could not be claimed. The request remains available until it expires.</p> : null}
      {activeLease && activeRequestId ? (
        <div className="hbv-active-section">
          <div className="hbv-active-header">
            <div className="hbv-active-header__info">
              <h2>Controlling browser</h2>
              {activeAction ? <RequestContext action={activeAction} runId={run.id} /> : null}
              <p>{activeAction?.instructions ?? "Complete the requested interaction within approved origins, then choose Done to return control to the agent."}</p>
              <p className="muted">Lease expires {new Date(activeLease.expires_at).toLocaleTimeString()}.</p>
            </div>
            <div className="button-row hbv-active-header__actions">
              <button className="primary-button" type="button" disabled={release.isPending || skip.isPending} onClick={() => release.mutate(activeRequestId)}>
                {release.isError ? "Retry Done—resume agent" : "Done—resume agent"}
              </button>
              <button className="secondary-button" type="button" disabled={skip.isPending || release.isPending} onClick={() => skip.mutate(activeRequestId)}>Skip this case/journey</button>
            </div>
          </div>
          {activeLease.viewer_available && activeLease.viewer_url && activeLease.viewer_ticket ? (
            <HumanBrowserViewer autoConnect url={activeLease.viewer_url} ticket={activeLease.viewer_ticket}
              onReconnect={async () => {
                const grant = await api.reconnectHumanAction(activeRequestId, activeLease);
                const renewed = { ...activeLease, expires_at: grant.expires_at, viewer_url: grant.viewer_url, viewer_ticket: grant.viewer_ticket };
                activeLeaseRef.current = renewed;
                setActiveLease(renewed);
                return grant;
              }} />
          ) : (
            <p role="alert">The browser owner did not provide a secure viewer. Control remains unavailable.</p>
          )}
        </div>
      ) : null}
      {release.isError ? <p role="alert">Resume delivery failed. Retry Done to notify the worker. Agent control remains blocked until the handoff is verified.</p> : null}

      {skip.isError ? <p role="alert">Skip could not be confirmed. Retry Skip; the agent remains paused until browser control is safely revoked.</p> : null}

      {leased.map((action) => (
        <article className="study-summary" key={action.id}>
          <AlertTriangle aria-hidden="true" />
          <div>
            <h2>Browser control lease active</h2>
            <p>A live lease already owns this browser. If the operator disconnected, the lease expires automatically before control can be claimed again.</p>
            <p className="muted">Lease generation {action.control_generation}; expires {action.lease_expires_at ? new Date(action.lease_expires_at).toLocaleString() : "soon"}.</p>
          </div>
        </article>
      ))}

      {finished.map((action) => (
        <article className="study-summary" key={action.id}>
          <ShieldCheck aria-hidden="true" />
          <div>
            <h2>{action.status === "completed" ? ended ? "Human assistance completed" : "Human assistance completed; resuming" : action.status === "skipped" ? "Not tested—human assistance skipped" : `Human action ${action.status}`}</h2>
            <RequestContext action={action} runId={run.id} />
            <p>{action.request_type.replaceAll("_", " ")} · Request {action.id.slice(0, 8)}</p>
          </div>
        </article>
      ))}

      </section>
      <section className="human-action-group human-approval-group" aria-labelledby="approval-decisions-heading">
      <div className="section-heading">
        <div><p className="section-label">Sensitive actions</p><h2 id="approval-decisions-heading">Approval decisions</h2></div>
      </div>
      <p className="muted">Each decision applies to one recorded action. Approval does not authorize similar actions elsewhere.</p>
      {decisionMessage ? <p role="status" aria-live="polite">{decisionMessage}</p> : null}
      {approvals.isError ? <p role="alert">Approval requests could not be loaded.</p> : null}
      {pendingApprovals.map((item) => (
        <article className="study-summary" key={item.id}>
          <ShieldCheck aria-hidden="true" />
          <div>
            <h3>{item.action_summary}</h3>
            {item.journey_id && item.step_id ? <Link to={`/runs/${run.id}/journeys/${item.journey_id}?step=${item.step_id}`}>Review this action and preceding safe evidence</Link> : null}
            <p>Environment: {item.environment}. This approval applies only to this recorded action and expires {new Date(item.expires_at).toLocaleString()}.</p>
          </div>
          <div className="button-row">
            <button className="secondary-button" type="button" disabled={decision.isPending} onClick={() => decision.mutate({ id: item.id, approved: false })}>Reject</button>
            <button className="primary-button" type="button" disabled={decision.isPending} onClick={() => decision.mutate({ id: item.id, approved: true })}>Approve once</button>
          </div>
        </article>
      ))}
      {approvedActions.map((item) => <article className="study-summary approval-granted" key={item.id}>
        <ShieldCheck aria-hidden="true" />
        <div><h3>Approval granted · dispatch status pending</h3><p>{item.action_summary}</p>
          <p>Environment: {item.environment}. This one-time authorization does not mean the action was dispatched or completed. The worker must revalidate and consume its receipt.</p>
          {item.journey_id && item.step_id ? <Link to={`/runs/${run.id}/journeys/${item.journey_id}?step=${item.step_id}`}>Review the recorded step</Link> : null}
        </div>
      </article>)}
      {approvals.data?.length === 0 ? <p className="muted">No sensitive action is awaiting approval.</p> : null}
      {decision.isError ? <p role="alert">That approval is no longer available; refresh the page.</p> : null}
      </section>
      </> : null}

      <p className="muted">Enter login details only in the protected browser, using a dedicated test account. MarketTwin forwards your input to the browser; the agent is paused. Credential entry is not intentionally retained, and scoped session state may be held temporarily for this test. Never paste credentials into notes or chat.</p>
    </section>
  );
}

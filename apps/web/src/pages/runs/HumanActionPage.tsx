import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Clock3, ShieldCheck, UserRound } from "lucide-react";
import { Link, useOutletContext } from "react-router-dom";

import { RunContext } from "../../layouts/RunLayout";
import { api, type HumanLeaseGrant } from "../../lib/api";
import { HumanBrowserViewer } from "./HumanBrowserViewer";

export function HumanActionPage() {
  const { run } = useOutletContext<RunContext>();
  const actions = useQuery({
    queryKey: ["human-actions", run.id],
    queryFn: ({ signal }) => api.listHumanActions(run.id, signal),
    refetchInterval: 2500,
  });
  const queryClient = useQueryClient();
  const [activeLease, setActiveLease] = useState<HumanLeaseGrant | null>(null);
  const [activeRequestId, setActiveRequestId] = useState<string | null>(null);
  const releasingRef = useRef(false);
  const claim = useMutation({
    mutationFn: (requestId: string) => api.claimHumanAction(requestId),
    onSuccess: (lease, requestId) => {
      releasingRef.current = false;
      setActiveLease(lease);
      setActiveRequestId(requestId);
      queryClient.invalidateQueries({ queryKey: ["human-actions", run.id] });
    },
  });
  const renew = useMutation({
    mutationFn: ({ requestId, lease }: { requestId: string; lease: HumanLeaseGrant }) =>
      api.renewHumanAction(requestId, lease),
    onSuccess: ({ expires_at }) => {
      setActiveLease((lease) => lease ? { ...lease, expires_at } : lease);
    },
    onError: () => {
      if (releasingRef.current) return;
      setActiveLease(null);
      setActiveRequestId(null);
      queryClient.invalidateQueries({ queryKey: ["human-actions", run.id] });
    },
  });
  const release = useMutation({
    onMutate: () => { releasingRef.current = true; },
    mutationFn: ({ requestId, lease }: { requestId: string; lease: HumanLeaseGrant }) =>
      api.releaseHumanAction(requestId, lease),
    onSuccess: () => {
      releasingRef.current = false;
      setActiveLease(null);
      setActiveRequestId(null);
      queryClient.invalidateQueries({ queryKey: ["human-actions", run.id] });
    },
  });
  const cancel = useMutation({
    mutationFn: (requestId: string) => api.cancelHumanAction(requestId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["human-actions", run.id] }),
  });
  const approvals = useQuery({
    queryKey: ["action-approvals", run.id],
    queryFn: ({ signal }) => api.listActionApprovals(run.id, signal),
    refetchInterval: 2500,
  });
  const decision = useMutation({
    mutationFn: ({ id, approved }: { id: string; approved: boolean }) =>
      api.decideActionApproval(id, approved),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["action-approvals", run.id] }),
  });
  const pending = actions.data?.filter((item) => item.status === "pending") ?? [];
  const leased = actions.data?.filter((item) => item.status === "leased") ?? [];
  const finished = actions.data?.filter((item) => ["completed", "cancelled", "expired"].includes(item.status)) ?? [];

  useEffect(() => {
    if (!activeLease || !activeRequestId || release.isPending || release.isError) return;
    const timer = window.setInterval(() => {
      renew.mutate({ requestId: activeRequestId, lease: activeLease });
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [activeLease, activeRequestId, release.isPending, release.isError]);

  return (
    <section className="results-boundary" aria-labelledby="human-action-heading">
      <p className="section-label">Human assistance</p>
      <h1 id="human-action-heading">Continue in the test browser</h1>
      <p>MarketTwin pauses the agent while an authorized operator handles login, MFA, SSO, CAPTCHA, or another protected step.</p>

      {actions.isPending ? <p role="status">Checking for a human action request…</p> : null}
      {actions.isError ? <p role="alert">Human action status is unavailable. Retry this page in a moment.</p> : null}
      {actions.isSuccess && actions.data.length === 0 ? (
        <div className="empty-state">
          <Clock3 aria-hidden="true" />
          <h2>Waiting for the test</h2>
          <p>No human action is currently required. This page updates as the run progresses.</p>
        </div>
      ) : null}

      {pending.map((action) => (
        <article className="study-summary" key={action.id}>
          <UserRound aria-hidden="true" />
          <div>
            <h2>Awaiting human: {action.request_type.replaceAll("_", " ")}</h2>
            <p>The agent is paused. Taking control opens the same supervised browser context.</p>
            <p className="muted">Request expires {action.expires_at ? new Date(action.expires_at).toLocaleString() : "when the run ends"}.</p>
          </div>
          <div className="button-row">
            <button className="secondary-button" type="button" disabled={claim.isPending || Boolean(activeLease)} onClick={() => claim.mutate(action.id)}>
              <ShieldCheck size={16} aria-hidden="true" /> Take browser control
            </button>
            <button className="secondary-button" type="button" disabled={cancel.isPending} onClick={() => cancel.mutate(action.id)}>Cancel request</button>
          </div>
        </article>
      ))}

      {claim.isError ? <p role="alert">Browser control could not be claimed. The request remains available until it expires.</p> : null}
      {activeLease && activeRequestId ? (
        <article className="study-summary">
          <UserRound aria-hidden="true" />
          <div>
            <h2>Controlling browser</h2>
            <p>Complete the requested authentication in the protected browser, then release control for verification.</p>
            <p className="muted">Lease expires {new Date(activeLease.expires_at).toLocaleTimeString()}.</p>
            {activeLease.viewer_available && activeLease.viewer_url && activeLease.viewer_ticket ? (
              <HumanBrowserViewer url={activeLease.viewer_url} ticket={activeLease.viewer_ticket}
                onReconnect={async () => {
                  const grant = await api.reconnectHumanAction(activeRequestId, activeLease);
                  setActiveLease((lease) => lease ? { ...lease, expires_at: grant.expires_at } : lease);
                  return grant;
                }} />
            ) : (
              <p role="alert">The browser owner did not provide a secure viewer. Control remains unavailable.</p>
            )}
            <button className="primary-button" type="button" disabled={release.isPending} onClick={() => release.mutate({ requestId: activeRequestId, lease: activeLease })}>
              Release control for verification
            </button>
          </div>
        </article>
      ) : null}
      {release.isError ? <p role="alert">Release delivery failed. Retry Release to notify the worker. Agent control remains blocked until the handoff is verified.</p> : null}

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
            <h2>{action.status === "completed" ? "Authentication verified; resuming" : `Human action ${action.status}`}</h2>
            <p>{action.request_type.replaceAll("_", " ")} · Request {action.id.slice(0, 8)}</p>
          </div>
        </article>
      ))}

      <div className="section-heading">
        <div><p className="section-label">Sensitive actions</p><h2>Approval decisions</h2></div>
      </div>
      {approvals.isError ? <p role="alert">Approval requests could not be loaded.</p> : null}
      {approvals.data?.filter((item) => item.status === "pending").map((item) => (
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
      {approvals.data?.length === 0 ? <p className="muted">No sensitive action is awaiting approval.</p> : null}
      {decision.isError ? <p role="alert">That approval is no longer available; refresh the page.</p> : null}

      <p className="muted">Passwords, one-time codes, browser frames, and page contents must only be sent through the protected browser viewer. Never paste them into MarketTwin notes or chat.</p>
    </section>
  );
}

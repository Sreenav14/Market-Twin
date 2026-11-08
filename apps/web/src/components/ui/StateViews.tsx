import { ReactNode, useEffect, useState } from "react";
import { Inbox } from "lucide-react";
import { InlineAlert } from "./Feedback";

/* Loading timing law (Spec 4 §1.2, adopted interim Q10/Q11):
   show-delay 300ms — an operation that finishes sooner never
   flashes an indicator; minimum-display 500ms — once shown, an
   indicator stays at least this long so it reads as feedback,
   not a glitch. The 30s house fetch ceiling lives in lib/api
   (AbortController) and surfaces as the §4 error state. */
export const LOADING_SHOW_DELAY_MS = 300;
export const LOADING_MIN_DISPLAY_MS = 500;

export function useDelayedLoading(active: boolean): boolean {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!active) return;
    const t = window.setTimeout(() => setShown(true), LOADING_SHOW_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [active]);
  useEffect(() => {
    if (active || !shown) return;
    const t = window.setTimeout(() => setShown(false), LOADING_MIN_DISPLAY_MS);
    return () => window.clearTimeout(t);
  }, [active, shown]);
  return shown;
}

/* The indeterminate spinner — the system's ONLY loop (1000ms
   linear, states.css). It stops under reduced motion, where the
   static arc + the visible label carry the state. Sizes ride
   the icon ladder: 16 inline / 20 region / 32 page. */
export function Spinner({ size = 16 }: { size?: 16 | 20 | 32 }) {
  return (
    <span
      className={size === 32 ? "spinner spinner-lg" : "spinner"}
      style={size === 20 ? { width: 20, height: 20 } : undefined}
      aria-hidden="true"
    />
  );
}

export function LoadingPanel({ label = "Loading" }: { label?: string }) {
  return (
    <div className="panel state-panel" role="status">
      <Spinner size={20} />
      <span>{label}…</span>
    </div>
  );
}

/* Static skeleton (Spec 4 §1.5) — a wireframe of the real
   layout for stable-layout surfaces only. Bars and blocks only:
   no text, no numbers, no fake rows. It NEVER animates.
   Excluded by design: the run view (its layout grows during
   discovery — it shows counts + status words instead), modals,
   toasts, and any surface whose final layout is not known. */
export function SkeletonPanel({ rows = 3, label }: { rows?: number; label: string }) {
  return (
    <div className="panel skeleton" role="status" aria-label={label}>
      <div className="skeleton-bar skeleton-bar-title" aria-hidden="true" />
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton-row" key={i} aria-hidden="true">
          <div className="skeleton-avatar" />
          <div className={`skeleton-bar${i === rows - 1 ? " skeleton-bar-short" : ""}`} />
        </div>
      ))}
    </div>
  );
}

export function ErrorPanel({
  message,
  action,
}: {
  message: string;
  action?: ReactNode;
}) {
  // Phase 2d: the load-failure alert is the feedback ladder's ONE
  // inline-alert recipe (rung 4) — it keeps role="alert" because it
  // is the sole announcement channel for a failed load.
  return (
    <InlineAlert severity="error" title="We couldn’t load this view." role="alert" action={action}>
      {message}
    </InlineAlert>
  );
}

/* Empty states: ONE recipe (Spec 4 §3) — optional 32px icon,
   positive-statement title, 1–2 line body, and an action ONLY
   where a real action exists (first-run / no-results recovery).
   Cleared/all-done states pass no action. No illustrations. */
export function EmptyState({
  title,
  copy,
  action,
  icon,
}: {
  title: string;
  copy: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-mark" aria-hidden="true">
        {icon ?? <Inbox size={32} strokeWidth={1.7} />}
      </div>
      <h2>{title}</h2>
      <p>{copy}</p>
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

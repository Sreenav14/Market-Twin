import { ReactNode } from "react";

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

export function LoadingPanel({ label = "Loading" }: { label?: string }) {
  return <div className="panel state-panel" role="status"><Spinner /><span>{label}…</span></div>;
}

export function ErrorPanel({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="error-panel" role="alert">
      <div><strong>We couldn’t load this view.</strong><span>{message}</span></div>
      {action ? <div>{action}</div> : null}
    </div>
  );
}

export function EmptyState({ title, copy, action }: { title: string; copy: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-mark" aria-hidden="true">—</div>
      <h2>{title}</h2>
      <p>{copy}</p>
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

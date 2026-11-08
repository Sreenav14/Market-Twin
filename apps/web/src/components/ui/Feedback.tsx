import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
  type Ref,
} from "react";
import { CircleCheck, Info, OctagonX, TriangleAlert, X } from "lucide-react";

/* Feedback ladder — Phase 2d, Spec 3 §8/§9. ONE system, first match:
   field error → group error → error summary → inline alert → toast →
   banner → dialog. Binding rules: NO error toasts, ever; nothing the
   user still needs ever auto-expires; toasts are for completed
   background actions and appear instantly (no arrival animation —
   only stack shift/exit move); severity is always icon + word +
   tint, never colour alone. Severity title words are the adopted
   feedback subset (owner question 3 interim): Information / Success /
   Warning / Error, carried as a visually-hidden prefix so the
   severity survives greyscale and screen readers alike. */

export type Severity = "info" | "success" | "warning" | "error";

const SEVERITY_WORD: Record<Severity, string> = {
  info: "Information",
  success: "Success",
  warning: "Warning",
  error: "Error",
};

function SeverityIcon({ severity }: { severity: Severity }) {
  const props = { size: 16, "aria-hidden": true } as const;
  switch (severity) {
    case "success":
      return <CircleCheck {...props} />;
    case "warning":
      return <TriangleAlert {...props} />;
    case "error":
      return <OctagonX {...props} />;
    default:
      return <Info {...props} />;
  }
}

/* Inline alert (rung 4): in-flow, at the section it belongs to.
   Dismissible only when the caller passes onDismiss — spec §8.3:
   success/info normally may; warning only if the warning persists
   elsewhere; an unresolved error never carries one. `role` is set
   by the caller only when this alert is the sole announcement
   channel for its event (in-flow content that loads with the page
   is not a live region). */
export function InlineAlert({
  severity,
  title,
  children,
  action,
  onDismiss,
  role,
  tabIndex,
  ref,
}: {
  severity: Severity;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  onDismiss?: () => void;
  role?: "alert";
  tabIndex?: number;
  ref?: Ref<HTMLDivElement>;
}) {
  return (
    <div ref={ref} className={`mt-inline-alert mt-inline-alert--${severity}`} role={role} tabIndex={tabIndex}>
      <span className="mt-alert-icon">
        <SeverityIcon severity={severity} />
      </span>
      <div className="mt-alert-text">
        <p className="mt-alert-title">
          <span className="visually-hidden">{SEVERITY_WORD[severity]}: </span>
          {title}
        </p>
        {children ? <div className="mt-alert-body">{children}</div> : null}
        {action ? <div className="mt-alert-action">{action}</div> : null}
      </div>
      {onDismiss ? (
        <button
          type="button"
          className="mt-alert-close"
          aria-label="Dismiss notification"
          onClick={onDismiss}
        >
          <X size={16} aria-hidden="true" />
        </button>
      ) : null}
    </div>
  );
}

/* Banner (rung 6): page-level, pushes content down, one at a time,
   role="alert", and NOT dismissible — it disappears when the
   condition ends (Spec §8.3, Atlassian). */
export function Banner({
  severity,
  title,
  children,
  action,
  titleAs = "p",
}: {
  severity: Severity;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  // Surfaces whose banner carried the section heading keep it —
  // the recipe governs the look, not the document outline.
  titleAs?: "p" | "h2";
}) {
  const Title = titleAs;
  return (
    <div className={`mt-banner mt-inline-alert--${severity}`} role="alert">
      <span className="mt-alert-icon">
        <SeverityIcon severity={severity} />
      </span>
      <div className="mt-alert-text">
        <Title className="mt-alert-title">
          {titleAs === "p" ? <span className="visually-hidden">{SEVERITY_WORD[severity]}: </span> : null}
          {title}
        </Title>
        {children ? <div className="mt-alert-body">{children}</div> : null}
      </div>
      {action ? <div className="mt-alert-action">{action}</div> : null}
    </div>
  );
}

/* Toasts (rung 5): success/info/warning only — the type excludes
   "error", so an error toast is unrepresentable. A toast is a
   disposable duplicate of a persistent truth (the result is already
   visible or recorded where it belongs). 8s auto-dismiss, 10s with
   an action, paused while hovered or focused (WCAG 2.2.1
   mitigation). Max 3 visible; the rest queue. */
export type ToastSeverity = Exclude<Severity, "error">;

export interface ToastInput {
  severity?: ToastSeverity;
  title: string;
  body?: string;
  action?: { label: string; onClick: () => void };
}

interface ToastItem extends ToastInput {
  id: number;
  severity: ToastSeverity;
}

const ToastContext = createContext<{ toast: (input: ToastInput) => void } | null>(null);

export function useToast() {
  const context = useContext(ToastContext);
  // Pages rendered outside the provider (unit tests, embeds) degrade
  // to a no-op rather than crashing — the persistent copy of the
  // outcome still exists at its own surface.
  return context ?? { toast: () => {} };
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, { handle: number; expiresAt: number; remaining: number }>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) window.clearTimeout(timer.handle);
    timers.current.delete(id);
    setToasts((previous) => previous.filter((item) => item.id !== id));
  }, []);

  const schedule = useCallback(
    (id: number, delay: number) => {
      const handle = window.setTimeout(() => dismiss(id), delay);
      timers.current.set(id, { handle, expiresAt: Date.now() + delay, remaining: delay });
    },
    [dismiss],
  );

  const pause = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (!timer) return;
    window.clearTimeout(timer.handle);
    timer.remaining = Math.max(0, timer.expiresAt - Date.now());
  }, []);

  const resume = useCallback(
    (id: number) => {
      const timer = timers.current.get(id);
      if (!timer) return;
      schedule(id, timer.remaining);
    },
    [schedule],
  );

  const toast = useCallback(
    (input: ToastInput) => {
      const id = nextId.current++;
      const item: ToastItem = { ...input, id, severity: input.severity ?? "success" };
      setToasts((previous) => [...previous, item]);
      schedule(id, input.action ? 10_000 : 8_000);
    },
    [schedule],
  );

  const visible = toasts.slice(-3);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="mt-toast-region" role="status" aria-live="polite">
        {visible.map((item) => (
          <div
            key={item.id}
            className={`mt-toast mt-inline-alert--${item.severity}`}
            onMouseEnter={() => pause(item.id)}
            onMouseLeave={() => resume(item.id)}
            onFocus={() => pause(item.id)}
            onBlur={() => resume(item.id)}
          >
            <span className="mt-alert-icon">
              <SeverityIcon severity={item.severity} />
            </span>
            <div className="mt-alert-text">
              <p className="mt-alert-title">
                <span className="visually-hidden">{SEVERITY_WORD[item.severity]}: </span>
                {item.title}
              </p>
              {item.body ? <p className="mt-alert-body">{item.body}</p> : null}
              {item.action ? (
                <button
                  type="button"
                  className="mt-toast-action"
                  onClick={() => {
                    item.action!.onClick();
                    dismiss(item.id);
                  }}
                >
                  {item.action.label}
                </button>
              ) : null}
            </div>
            <button
              type="button"
              className="mt-toast-close"
              aria-label="Dismiss notification"
              onClick={() => dismiss(item.id)}
            >
              <X size={16} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useRef, type ReactNode, type RefObject } from "react";

/* ONE dialog primitive (Phase 2c, Spec 2 §3/§4/§6) on Radix Dialog:
   focus trap + inert background + Esc + focus return come from the
   primitive, never hand-rolled. Sizes are the adopted scale
   360/560/720 (owner question 7 interim). Dismissal grammar (§3.6):
   pristine surfaces dismiss freely via Esc/×/scrim; a DIRTY form
   routes every dismissal gesture to onDirtyAttempt (the Tier-1
   discard confirmation) instead of closing; a confirmation
   (alert) ignores scrim clicks. Initial focus is the caller's
   named element — safe action for destructive confirmations,
   primary/first field for benign ones (§3.5, owner question 4
   interim split). No arrival animation beyond the register:
   entry is the overlay fade only (owner question 2 interim). */

export type DialogSize = "sm" | "md" | "lg";

export function Dialog({
  open,
  onOpenChange,
  trigger,
  title,
  description,
  size = "md",
  alert = false,
  form = false,
  dirty = false,
  onDirtyAttempt,
  busy = false,
  initialFocusRef,
  hideClose = false,
  titleVisuallyHidden = false,
  children,
  footer,
  contentProps,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  size?: DialogSize;
  alert?: boolean;
  form?: boolean;
  dirty?: boolean;
  onDirtyAttempt?: () => void;
  busy?: boolean;
  initialFocusRef?: RefObject<HTMLElement | null>;
  hideClose?: boolean;
  titleVisuallyHidden?: boolean;
  children?: ReactNode;
  footer?: ReactNode;
  contentProps?: React.ComponentProps<typeof DialogPrimitive.Content>;
}) {
  const fallbackFocus = useRef<HTMLDivElement>(null);

  const handleOpenChange = (value: boolean) => {
    if (!value && dirty && !busy) {
      onDirtyAttempt?.();
      return;
    }
    if (!value && busy) return;
    onOpenChange(value);
  };

  return (
    <DialogPrimitive.Root open={open} onOpenChange={handleOpenChange}>
      {trigger ? <DialogPrimitive.Trigger asChild>{trigger}</DialogPrimitive.Trigger> : null}
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay" />
        <DialogPrimitive.Content
          {...contentProps}
          {...(alert ? { role: "alertdialog" as const } : {})}
          className={`mt-dialog mt-dialog--${size}${form ? " mt-dialog--form" : ""}${alert ? " mt-dialog--confirm" : ""} ${contentProps?.className ?? ""}`.trim()}
          onOpenAutoFocus={(event) => {
            if (initialFocusRef) {
              event.preventDefault();
              initialFocusRef.current?.focus();
            }
            contentProps?.onOpenAutoFocus?.(event);
          }}
          onPointerDownOutside={(event) => {
            /* Confirmations: a stray scrim click answers nothing (§3.6). */
            if (alert) event.preventDefault();
            contentProps?.onPointerDownOutside?.(event);
          }}
        >
          <div className="mt-dialog-header">
            <DialogPrimitive.Title className={titleVisuallyHidden ? "visually-hidden" : "mt-dialog-title"}>
              {title}
            </DialogPrimitive.Title>
            {description ? (
              <DialogPrimitive.Description className="mt-dialog-description">
                {description}
              </DialogPrimitive.Description>
            ) : null}
          </div>
          {!hideClose ? (
            <DialogPrimitive.Close className="mt-dialog-close" aria-label="Close dialog" disabled={busy}>
              <X size={16} aria-hidden="true" />
            </DialogPrimitive.Close>
          ) : null}
          <div className="mt-dialog-body" ref={fallbackFocus}>
            {children}
          </div>
          {footer ? <div className="mt-dialog-footer">{footer}</div> : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/** The discard confirmation (Spec 2 §6 Tier 1) for dirty dialogs:
    safe action ("Keep editing") takes initial focus. */
export function DiscardChangesDialog({
  open,
  onKeep,
  onDiscard,
}: {
  open: boolean;
  onKeep: () => void;
  onDiscard: () => void;
}) {
  const keepRef = useRef<HTMLButtonElement>(null);
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => { if (!value) onKeep(); }}
      title="Discard changes?"
      description="Your changes have not been saved. Discarding them cannot be undone."
      size="sm"
      alert
      initialFocusRef={keepRef}
      footer={
        <>
          <button ref={keepRef} type="button" className="secondary-button" onClick={onKeep}>
            Keep editing
          </button>
          <button type="button" className="danger-button" onClick={onDiscard}>
            Discard changes
          </button>
        </>
      }
    />
  );
}

import * as PopoverPrimitive from "@radix-ui/react-popover";
import { X } from "lucide-react";
import type { ReactElement, ReactNode } from "react";

/* ONE popover recipe (Phase 2c, Spec 2 §8.5/§8.6): click-triggered,
   NON-modal anchored panel for supplementary content that may be
   interactive (a link, a control, a mini-form). Focus moves in on
   open, is NOT trapped, Esc closes and returns focus, focus-out
   closes. If a task needs a trap, it is a Dialog, not a popover.
   Width 320 (400 wide variant), padding 16, radius 8, anchored
   elevation — the same language as menus. */
export function Popover({
  trigger,
  title,
  children,
  wide = false,
  label,
}: {
  trigger: ReactElement;
  title?: string;
  children: ReactNode;
  wide?: boolean;
  label: string;
}) {
  return (
    <PopoverPrimitive.Root>
      <PopoverPrimitive.Trigger asChild>{trigger}</PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          className={`mt-popover${wide ? " mt-popover--wide" : ""}`}
          sideOffset={8}
          aria-label={label}
        >
          {title ? <p className="mt-popover-title">{title}</p> : null}
          {children}
          <PopoverPrimitive.Close className="mt-dialog-close" aria-label="Close popover">
            <X size={16} aria-hidden="true" />
          </PopoverPrimitive.Close>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}

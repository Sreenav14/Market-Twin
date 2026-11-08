import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import type { ReactElement } from "react";

/* ONE tooltip recipe (Phase 2c, Spec 2 \u00a78.2): plain text only,
   \u2264120 chars, inverse surface, fade 110ms, hover delay 400ms
   (adopted interim \u2014 NN/g 300\u2013500 window, not Radix's 700),
   instant on keyboard focus, 300ms skip-delay between siblings.
   Never on a disabled control, never interactive content \u2014
   that is ui/Popover's job. */

export function Tooltip({
  children,
  text,
}: {
  children: ReactElement;
  text: string;
}) {
  return (
    <TooltipPrimitive.Provider delayDuration={400} skipDelayDuration={300}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content className="tooltip" sideOffset={6}>
            {text}
            <TooltipPrimitive.Arrow />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}

import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import type { ReactElement } from "react";

export function Tooltip({ children, text }: { children: ReactElement; text: string }) {
  return <TooltipPrimitive.Provider delayDuration={350}><TooltipPrimitive.Root>
    <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
    <TooltipPrimitive.Portal><TooltipPrimitive.Content className="tooltip" sideOffset={6}>
      {text}<TooltipPrimitive.Arrow />
    </TooltipPrimitive.Content></TooltipPrimitive.Portal>
  </TooltipPrimitive.Root></TooltipPrimitive.Provider>;
}

import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export const buttonVariants = cva("ui-button", {
  variants: {
    variant: { default: "primary-button", secondary: "secondary-button", ghost: "ghost-button", destructive: "danger-button" },
    size: { default: "", sm: "compact", icon: "button-square" },
  },
  defaultVariants: { variant: "default", size: "default" },
});

export function Button({ className, variant, size, type = "button", ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>) {
  return <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

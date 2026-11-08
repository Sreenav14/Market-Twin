import type { ReactNode } from "react";

/**
 * The one card/panel primitive (Phase 2b, Spec 1 §1).
 * `panel` = a layout region (24px padding). `card` = one self-contained
 * subject (16px padding). `sunken` = the filled well variant, for use
 * inside a panel only. The skin lives in styles/display.css — the only
 * definition of the recipe. Static cards have no hover state.
 */
export function Card({
  variant = "card",
  className = "",
  children,
  ...rest
}: {
  variant?: "card" | "panel" | "sunken";
  className?: string;
  children: ReactNode;
} & React.HTMLAttributes<HTMLElement>) {
  const cls =
    variant === "panel" ? "panel" : variant === "sunken" ? "card-sunken" : "card";
  return (
    <section className={`${cls} ${className}`.trim()} {...rest}>
      {children}
    </section>
  );
}

import { useState } from "react";
import { Icon } from "./Icon";

/**
 * The one identity tile (Phase 2b, Spec 1 §5).
 * SHAPE RULE (binding): people are CIRCLES; personas and apps are
 * SQUARES (6px radius) — shape alone stops a simulated tester's quote
 * reading as human testimony. Ladder: xs 16 / sm 24 / md 32 (default) /
 * lg 40 / xl 48. Initials: two at 24px+, one at 20px, none at 16px
 * (generic glyph). A failed image swaps once to the fallback and stays.
 */
export type AvatarKind = "person" | "persona" | "app";
export type AvatarSize = "xs" | "sm" | "md" | "lg" | "xl";

const PX: Record<AvatarSize, number> = { xs: 16, sm: 24, md: 32, lg: 40, xl: 48 };

function initialsFor(name: string, px: number): string {
  if (px < 20) return "";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "";
  if (px < 24 || parts.length === 1) return parts[0][0]!.toUpperCase();
  return (parts[0][0]! + parts[parts.length - 1][0]!).toUpperCase();
}

export function Avatar({
  kind,
  name,
  src,
  size = "md",
  tint,
}: {
  kind: AvatarKind;
  name: string;
  src?: string;
  size?: AvatarSize;
  /** Deterministic per-identity tint (personas carry their series colour). */
  tint?: string;
}) {
  const [failed, setFailed] = useState(false);
  const px = PX[size];
  const initials = initialsFor(name, px);
  return (
    <span
      className={`avatar avatar-${kind} avatar-${size}`}
      style={tint ? { background: tint } : undefined}
      aria-hidden="true"
    >
      {src && !failed ? (
        <img src={src} alt="" onError={() => setFailed(true)} />
      ) : initials ? (
        <span className="avatar-initials">{initials}</span>
      ) : (
        <Icon name={kind === "person" ? "user" : "apps"} size={Math.round(px * 0.55)} />
      )}
    </span>
  );
}

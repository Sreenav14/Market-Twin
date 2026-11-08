import React from "react";

// Renamed in Phase 2b: the canonical `StatusPill` is the signed-in
// primitive in components/ui/StatusBadge.tsx. This concept/demo pill
// keeps its own name so an import can never be ambiguous.

export type ConceptStatus =
  | "Worked"
  | "Broken"
  | "Could not check"
  | "Not checked";

interface ConceptStatusPillProps {
  status: ConceptStatus;
  className?: string;
}

const STATUS_CONFIG: Record<
  ConceptStatus,
  { symbol: string; bg: string; text: string; word: string }
> = {
  Worked: {
    symbol: "✓",
    bg: "var(--works-tint)",
    text: "var(--works)",
    word: "Worked",
  },
  Broken: {
    symbol: "✕",
    bg: "var(--broken-tint)",
    text: "var(--broken)",
    word: "Broken",
  },
  "Could not check": {
    symbol: "?",
    bg: "var(--couldnot-tint)",
    text: "var(--couldnot)",
    word: "Could not check",
  },
  "Not checked": {
    symbol: "–",
    bg: "var(--notchecked-tint)",
    text: "var(--notchecked)",
    word: "Not checked",
  },
};

export const ConceptStatusPill: React.FC<ConceptStatusPillProps> = ({ status, className = "" }) => {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG["Not checked"];

  return (
    <span
      className={`inline-flex items-center gap-1 font-grid-cell ${className}`}
      style={{
        minHeight: "24px",
        padding: "4px 12px",
        borderRadius: "999px",
        backgroundColor: config.bg,
        color: config.text,
        fontWeight: 600,
        fontSize: "13px",
        lineHeight: "18px",
        whiteSpace: "nowrap",
      }}
    >
      <span aria-hidden="true" style={{ fontSize: "12px" }}>
        {config.symbol}
      </span>
      <span>{config.word}</span>
    </span>
  );
};

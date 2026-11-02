import React from "react";

interface ProofChipProps {
  screenshots?: number | null;
  rechecked?: boolean;
  text?: string;
  className?: string;
}

export const ProofChip: React.FC<ProofChipProps> = ({
  screenshots,
  rechecked = true,
  text,
  className = "",
}) => {
  let mainText = "";
  if (text) {
    mainText = text;
  } else if (typeof screenshots === "number") {
    mainText = `${screenshots} screenshots · re-checked`;
  } else {
    mainText = "Proof attached · re-checked";
  }

  // If text already includes the symbol, don't duplicate
  const hasSymbol = mainText.includes("✓");
  const baseText = hasSymbol ? mainText.replace("✓", "").trim() : mainText;

  return (
    <div
      className={`font-mono-data inline-flex items-center gap-1 ${className}`}
      style={{
        color: "var(--ink-2)",
        fontSize: "12px",
        lineHeight: "18px",
      }}
    >
      <span>{baseText}</span>
      {rechecked && (
        <span
          aria-hidden="true"
          style={{
            color: "var(--works)",
            fontWeight: 600,
          }}
        >
          ✓
        </span>
      )}
    </div>
  );
};

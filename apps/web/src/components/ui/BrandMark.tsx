export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <svg
      className={compact ? "brand-mark brand-mark-compact" : "brand-mark"}
      viewBox="0 0 32 32"
      aria-hidden="true"
    >
      <path
        d="M13 5H5v22h8M19 5h8v22h-8"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
      />
      <path d="M12 12h8v8h-8z" fill="currentColor" />
    </svg>
  );
}

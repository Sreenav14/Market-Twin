export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <svg className={compact ? "brand-mark brand-mark-compact" : "brand-mark"} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="currentColor" />
      <path d="M8.5 20.5 12.8 11l3.6 6.4 2.5-4.7 4.6 7.8" fill="none" stroke="white" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
    </svg>
  );
}

/**
 * The one determinate progress recipe (Phase 2b, Spec 1 §8 family).
 * A progress bar states a COUNT of a named thing ("3 of 12 journeys"),
 * never a bare percentage score. Fill length animates by transform
 * (scaleX, --dur-bar 300ms) — width animation is outside the motion
 * register. Outcome composition (worked/broken/…) is NOT progress: it
 * is the StackedBar / OutcomeCoverageBar chart family.
 */
export function ProgressBar({
  value,
  max,
  label,
}: {
  value: number;
  max: number;
  /** Words for assistive tech, e.g. "3 of 12 journeys finished". */
  label: string;
}) {
  const fraction = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuetext={label}
      aria-label={label}
    >
      <div className="progress-fill" style={{ transform: `scaleX(${fraction})` }} />
    </div>
  );
}

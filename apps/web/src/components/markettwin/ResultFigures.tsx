import type { StatusTone } from "../../lib/status";

export interface BarSegment {
  key: string;
  word: string;
  count: number;
  tone: StatusTone;
}

/**
 * One horizontal stacked bar (research rules: length/position encoding only,
 * count printed on every segment, direct labels under the bar — no legend,
 * zero-count buckets stay named in the label row, never hidden).
 * When `onSelect` is given, the label row becomes the control set and the
 * bar segments are clickable too; the filter state is stated in words by
 * the caller, not by colour alone.
 */
export function StackedBar({
  segments,
  total,
  unit,
  selected,
  onSelect,
  small = false,
  showLabels = true,
}: {
  segments: BarSegment[];
  total: number;
  unit: string;
  selected?: string | null;
  onSelect?: (key: string | null) => void;
  small?: boolean;
  showLabels?: boolean;
}) {
  const visible = segments.filter((segment) => segment.count > 0);
  const interactive = typeof onSelect === "function";
  return (
    <div className="rf-figure">
      <div className={`rf-bar${small ? " rf-bar-sm" : ""}`} aria-hidden="true">
        {visible.map((segment) => {
          const share = total > 0 ? segment.count / total : 0;
          return (
            <div
              key={segment.key}
              className={`rf-seg rf-seg-${segment.tone}${interactive ? " rf-seg-button" : ""}${selected === segment.key ? " rf-seg-selected" : ""}`}
              style={{ flexGrow: segment.count }}
              onClick={interactive ? () => onSelect(selected === segment.key ? null : segment.key) : undefined}
              /* No native title here (Phase 2c): this bar is aria-hidden
                 decoration; the same words are visible in the labels
                 below, and a tooltip repeating them is pollution
                 (Spec 2 \u00a78.1). */
            >
              {!small && share >= 0.3 ? (
                <span className="rf-seg-label">{segment.word} · {segment.count}</span>
              ) : !small && share >= 0.09 ? (
                <span className="rf-seg-label">{segment.count}</span>
              ) : null}
            </div>
          );
        })}
        {visible.length === 0 ? <div className="rf-seg rf-seg-notchecked" style={{ flexGrow: 1 }} /> : null}
      </div>
      {showLabels ? (
        <div className="rf-labels">
          {segments.map((segment) =>
            interactive ? (
              <button
                key={segment.key}
                type="button"
                className={`rf-label-button${selected === segment.key ? " rf-label-active" : ""}`}
                aria-pressed={selected === segment.key}
                aria-label={`${segment.word}: ${segment.count} of ${total} ${unit}. ${selected === segment.key ? "Clear the filter" : `Show only ${segment.word.toLowerCase()}`}.`}
                onClick={() => onSelect(selected === segment.key ? null : segment.key)}
              >
                <span className={`rf-swatch rf-seg-${segment.tone}`} aria-hidden="true" />
                {segment.word} · {segment.count} of {total}
              </button>
            ) : (
              <span key={segment.key} className="rf-label">
                <span className={`rf-swatch rf-seg-${segment.tone}`} aria-hidden="true" />
                {segment.word} · {segment.count} of {total}
              </span>
            ),
          )}
        </div>
      ) : null}
    </div>
  );
}

/** Coverage: tested length against the full discovered length, counts on both parts. */
export function CoverageProgress({ tested, discovered }: { tested: number; discovered: number }) {
  return (
    <StackedBar
      total={discovered}
      unit="features"
      segments={[
        { key: "tested", word: "Tested", count: tested, tone: "works" },
        { key: "not-tested", word: "Not tested", count: Math.max(0, discovered - tested), tone: "notchecked" },
      ]}
    />
  );
}

/** The same two-part encoding used inside every tester panel (small multiples: identical scale and order). */
export function JourneyMeter({ completed, attempted }: { completed: number; attempted: number }) {
  return (
    <StackedBar
      small
      showLabels={false}
      total={attempted}
      unit="journeys"
      segments={[
        { key: "completed", word: "Completed", count: completed, tone: "works" },
        { key: "not-completed", word: "Not completed", count: Math.max(0, attempted - completed), tone: "notchecked" },
      ]}
    />
  );
}

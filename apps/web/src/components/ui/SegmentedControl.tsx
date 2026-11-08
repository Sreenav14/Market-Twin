import { useRef, type ReactNode } from "react";

/* ONE segmented recipe (Phase 2c, Spec 2 §7.5/§7.6): a radio
   group — role="radiogroup" + role="radio" + aria-checked, roving
   tabindex, arrows/Home/End move AND check (APG Radio Group).
   Same content, different presentation — never tab semantics.
   Visual form: the reconciled inset-thumb / Prody track
   (overlays.css §1b). */

export interface SegmentedOption<T extends string> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
}

export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
  disabled = false,
  size = "md",
  className = "",
}: {
  label: string;
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
  size?: "md" | "lg";
  className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const enabled = options.map((o, i) => (!o.disabled && !disabled ? i : -1)).filter((i) => i >= 0);

  function move(from: number, key: string) {
    if (!enabled.length) return;
    let next: number | undefined;
    if (key === "Home") next = enabled[0];
    else if (key === "End") next = enabled[enabled.length - 1];
    else if (key === "ArrowRight" || key === "ArrowDown") {
      next = enabled[(enabled.indexOf(from) + 1 + enabled.length) % enabled.length] ?? enabled[0];
    } else if (key === "ArrowLeft" || key === "ArrowUp") {
      next = enabled[(enabled.indexOf(from) - 1 + enabled.length) % enabled.length] ?? enabled[enabled.length - 1];
    }
    if (next === undefined) return;
    onChange(options[next].value);
    refs.current[next]?.focus();
  }

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={`segmented-control${size === "lg" ? " segmented-control--lg" : ""} ${className}`.trim()}
    >
      {options.map((option, i) => {
        const checked = option.value === value;
        return (
          <button
            key={option.value}
            ref={(el) => { refs.current[i] = el; }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            disabled={disabled || option.disabled}
            className={`segmented-control-item${checked ? " active" : ""}`}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => {
              if (["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
                event.preventDefault();
                move(i, event.key);
              } else if (event.key === " " && !checked) {
                event.preventDefault();
                onChange(option.value);
              }
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

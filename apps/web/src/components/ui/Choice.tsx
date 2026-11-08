import { useEffect, useId, useRef, type InputHTMLAttributes, type ReactNode } from "react";

/* Choice controls — Phase 2d, Spec 3 §2/§3/§4. ONE recipe per job:
   - Checkbox: independent selections, effect on submit/save.
     18px box, indeterminate is a computed group-parent state only.
   - Radio: exactly one of a visible set; native same-name inputs
     give the APG group behaviour (one tab stop, arrows move+check).
   - Switch: immediate-effect settings ONLY — a switch inside a
     Save form is a checkbox in a costume (programme ruling). A
     switch always renders its state as the words "On"/"Off".
   All three are native inputs/buttons under the skin, so keyboard,
   form participation and screen-reader state come from the platform.
   The visual recipe lives in forms.css §2 (.mt-checkbox/.mt-radio/
   .mt-switch); a bare input can adopt it with the class alone. */

type ChoiceProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: ReactNode;
  hint?: ReactNode;
};

export function Checkbox({ label, hint, indeterminate = false, ...props }: ChoiceProps & { indeterminate?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return (
    <label className="mt-choice">
      <input ref={ref} type="checkbox" className="mt-checkbox" {...props} />
      <span className="mt-choice-text">
        {label}
        {hint ? <span className="mt-choice-hint">{hint}</span> : null}
      </span>
    </label>
  );
}

export function RadioGroup({
  legend,
  name,
  value,
  onChange,
  options,
  disabled = false,
}: {
  legend: ReactNode;
  name: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: ReactNode; hint?: ReactNode }[];
  disabled?: boolean;
}) {
  return (
    <fieldset className="mt-radio-group">
      <legend className="mt-group-label">{legend}</legend>
      <div className="mt-radio-items">
        {options.map((option) => (
          <label className="mt-choice" key={option.value}>
            <input
              type="radio"
              className="mt-radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              disabled={disabled}
              onChange={() => onChange(option.value)}
            />
            <span className="mt-choice-text">
              {option.label}
              {option.hint ? <span className="mt-choice-hint">{option.hint}</span> : null}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/* Switch — immediate effect only. `checked` is the setting's current
   (true) state: on a failed apply the caller reverts it and reports
   the failure inline (Spec §4.4) — the switch never shows a state
   the system does not hold. Pending shows "Saving…" text beside the
   control (the register has no loops, so no spinning thumb). */
export function Switch({
  label,
  hint,
  checked,
  onChange,
  pending = false,
  disabled = false,
}: {
  label: string;
  hint?: ReactNode;
  checked: boolean;
  onChange: (next: boolean) => void;
  pending?: boolean;
  disabled?: boolean;
}) {
  const labelId = useId();
  return (
    <div className="mt-switch-row">
      <span className="mt-switch-label" id={labelId}>{label}</span>
      {hint ? <span className="mt-choice-hint" id={`${labelId}-hint`}>{hint}</span> : null}
      <span className="mt-switch-control">
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          aria-labelledby={labelId}
          aria-describedby={hint ? `${labelId}-hint` : undefined}
          aria-busy={pending || undefined}
          disabled={disabled}
          className="mt-switch"
          data-state={checked ? "on" : "off"}
          onClick={() => onChange(!checked)}
        >
          <span className="mt-switch-thumb" aria-hidden="true" />
        </button>
        <span className="mt-switch-state" aria-hidden="true">
          {pending ? "Saving…" : checked ? "On" : "Off"}
        </span>
      </span>
    </div>
  );
}

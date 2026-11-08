import { useEffect, useRef, type ReactNode } from "react";
import { CircleAlert } from "lucide-react";

/* Form extras — Phase 2d, Spec 3 §1/§6. ONE recipe for labels, help
   and error text:
   - every field has a programmatic <label>; help and error text are
     linked with aria-describedby; invalid fields carry aria-invalid.
   - Required marking is in WORDS on both sides — "(required)" /
     "(optional)" suffixes in the label (Baymard: mark both explicitly;
     the asterisk-only 36-vs-4 split is retired). A form using
     "(required)" opens with the RequiredLegend line.
   - Field errors render the FieldError recipe: icon + text directly
     below the field, with a visually-hidden "Error:" prefix for
     screen readers (GOV.UK). A field error is NOT role="alert" —
     announcement on submit belongs to the ErrorSummary alone
     (one event, one announcement, Spec 3 §9.3).
   - Validation timing (programme ruling): punish late, reward early —
     nothing while typing, validate on blur, clear instantly once the
     value is fixed, ErrorSummary with focus on every failed submit. */

export function RequiredMark({ required }: { required: boolean }) {
  return (
    <span className="field-requirement">{required ? "(required)" : "(optional)"}</span>
  );
}

export function RequiredLegend() {
  return (
    <p className="form-required-legend">Fields marked (required) must be completed.</p>
  );
}

export function FieldError({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p id={id} className="field-error-text">
      <CircleAlert size={16} aria-hidden="true" />
      <span>
        <span className="visually-hidden">Error: </span>
        {children}
      </span>
    </p>
  );
}

export interface SummaryError {
  /** DOM id of the control (or first control of a group) the link focuses. */
  targetId: string;
  /** Wording identical to the inline FieldError beside the field. */
  message: string;
}

/* Error summary (Spec 3 §6.4, GOV.UK adapted to the SPA): appears on
   EVERY failed submit, takes keyboard focus, lists one link per error
   worded identically to the inline message; clicking a link moves
   focus to the field. While it is present the document title carries
   the "Error: " prefix; the original title is restored when the last
   error clears (the summary unmounts). */
export function ErrorSummary({ errors }: { errors: SummaryError[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const original = document.title;
    if (!original.startsWith("Error: ")) document.title = `Error: ${original}`;
    return () => {
      if (document.title === `Error: ${original}`) document.title = original;
    };
  }, []);
  if (!errors.length) return null;
  return (
    <div ref={ref} className="error-summary" role="alert" tabIndex={-1}>
      <h2 className="error-summary-heading">There is a problem</h2>
      <ul className="error-summary-list">
        {errors.map((error) => (
          <li key={error.targetId}>
            <a
              href={`#${error.targetId}`}
              onClick={(event) => {
                event.preventDefault();
                document.getElementById(error.targetId)?.focus();
              }}
            >
              {error.message}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* Per-field touched bookkeeping for the punish-late/reward-early
   timing: a field's error is visible once the field has been blurred
   or the form has been submitted; because errors are derived from the
   current value, a corrected field clears instantly. */
export function fieldErrorVisible(
  touched: ReadonlySet<string>,
  submitted: boolean,
  field: string,
): boolean {
  return submitted || touched.has(field);
}

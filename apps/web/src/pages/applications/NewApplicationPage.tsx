import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useOutletContext, useSearchParams } from "react-router-dom";
import { PageHeader } from "../../components/ui/PageHeader";
import { Spinner } from "../../components/ui/StateViews";
import { ErrorSummary, FieldError, RequiredLegend, RequiredMark } from "../../components/ui/Field";
import { InlineAlert } from "../../components/ui/Feedback";
import { api } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { AppShellContext } from "../../layouts/AppShell";

export function NewApplicationPage() {
  const navigate = useNavigate();
  const [parameters] = useSearchParams();
  const intakeUrl = parameters.get("url");
  const { workspace } = useOutletContext<AppShellContext>();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  // Punish late, reward early (Spec 3 §6.2): show on blur or submit,
  // clear instantly once fixed (the error is derived from the value).
  const [touched, setTouched] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  if (!canWriteWorkspace(workspace.role)) {
    return (
      <>
        <PageHeader eyebrow="Your apps" title="Add an app" />
        <InlineAlert severity="warning" title="Read-only workspace" action={<Link className="secondary-button" to="/applications">
              Back to your apps
            </Link>}>Your workspace role ({workspace.role}) cannot create applications.</InlineAlert>
      </>
    );
  }

  const nameError = (touched || submitted) && !name.trim()
    ? "Enter an application name."
    : name.length > 200
      ? "Enter an application name of 200 characters or fewer."
      : null;
  const summaryErrors = [
    ...(!name.trim() ? [{ targetId: "app-name", message: "Enter an application name." }] : []),
    ...(name.length > 200 ? [{ targetId: "app-name", message: "Enter an application name of 200 characters or fewer." }] : []),
  ];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setTouched(true);
    setSubmitted(true);
    if (!name.trim() || name.length > 200) return;

    setBusy(true);
    setError(null);
    try {
      const application = await api.createApplication(
        workspace.id,
        name.trim(),
        description.trim(),
      );
      if (mounted.current) navigate(intakeUrl
        ? `/applications/${application.id}/targets/new?url=${encodeURIComponent(intakeUrl)}`
        : `/applications/${application.id}`);
    } catch (submitError) {
      if (mounted.current) setError(
        submitError instanceof Error
          ? submitError.message
          : "Could not create application.",
      );
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Your apps"
        title="Add an app"
        description="Next you will add a target environment and authorize testing."
      />
      <div className="two-column-layout">
        <form className="panel form-grid form-card" onSubmit={submit} noValidate>
          {submitted && summaryErrors.length ? <ErrorSummary errors={summaryErrors} /> : null}
          <RequiredLegend />
          <div>
            <label className="field-label" htmlFor="app-name">
              Name <RequiredMark required />
            </label>
            <input
              id="app-name"
              className="text-input"
              value={name}
              disabled={busy}
              onChange={(event) => {
                setName(event.target.value);
                setError(null);
              }}
              onBlur={() => setTouched(true)}
              placeholder="e.g. Acme Storefront or Mobile Checkout"
              required
              maxLength={200}
              autoFocus
              aria-invalid={nameError ? true : undefined}
              aria-describedby={nameError ? "app-name-error" : undefined}
            />
            {nameError ? <FieldError id="app-name-error">{nameError}</FieldError> : null}
          </div>

          <div>
            <label className="field-label" htmlFor="app-description">
              Description <RequiredMark required={false} />
            </label>
            <textarea
              id="app-description"
              className="text-area"
              value={description}
              disabled={busy}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What user journey or service does this application cover?"
              rows={4}
            />
          </div>

          {error ? (
            <InlineAlert severity="error" title="Could not create application" role="alert">
              {error}
            </InlineAlert>
          ) : null}

          <div className="form-actions">
            <button className="secondary-button" type="button" disabled={busy} onClick={() => navigate("/applications")}>
              Cancel
            </button>
            <button
              className="primary-button"
              type="submit"
              disabled={busy}
            >
              {busy ? (
                <>
                  <Spinner /> Creating…
                </>
              ) : (
                "Add an app"
              )}
            </button>
          </div>
        </form>

        <aside className="info-card">
          <h2>Application boundary</h2>
          <p>
            An application organizes the targets, tests, and authorized execution scopes for a single product area.
          </p>
          <p style={{ marginTop: "12px" }}>
            After creating this container, you will register target URLs (such as staging or QA environments) and explicitly authorize browser testers to test them.
          </p>
        </aside>
      </div>
    </>
  );
}

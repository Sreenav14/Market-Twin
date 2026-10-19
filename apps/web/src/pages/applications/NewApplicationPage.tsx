import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { PageHeader } from "../../components/ui/PageHeader";
import { Spinner } from "../../components/ui/StateViews";
import { api } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { AppShellContext } from "../../layouts/AppShell";

export function NewApplicationPage() {
  const navigate = useNavigate();
  const { workspace } = useOutletContext<AppShellContext>();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [touched, setTouched] = useState(false);
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
        <PageHeader eyebrow="Applications" title="Create application" />
        <div className="error-panel" role="alert">
          <div>
            <strong>Read-only workspace</strong>
            <span>Your workspace role ({workspace.role}) cannot create applications.</span>
          </div>
          <div>
            <Link className="secondary-button" to="/applications">
              Back to applications
            </Link>
          </div>
        </div>
      </>
    );
  }

  const nameError = touched && !name.trim()
    ? "Application name is required."
    : name.length > 200
      ? "Application name cannot exceed 200 characters."
      : null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setTouched(true);
    if (!name.trim() || name.length > 200) return;

    setBusy(true);
    setError(null);
    try {
      const application = await api.createApplication(
        workspace.id,
        name.trim(),
        description.trim(),
      );
      if (mounted.current) navigate(`/applications/${application.id}`);
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
        eyebrow="Applications"
        title="Create application"
        description="Next you will add a target environment and authorize testing."
      />
      <div className="two-column-layout">
        <form className="panel form-grid form-card" onSubmit={submit} noValidate>
          <div>
            <label className="field-label" htmlFor="app-name">
              Name <span aria-hidden="true" style={{ color: "var(--danger)" }}>*</span>
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
              aria-invalid={nameError ? "true" : "false"}
              aria-describedby={nameError ? "app-name-error" : undefined}
            />
            {nameError ? (
              <p
                id="app-name-error"
                className="form-error"
                role="alert"
                style={{ marginTop: "4px" }}
              >
                {nameError}
              </p>
            ) : null}
          </div>

          <div>
            <label className="field-label" htmlFor="app-description">
              Description <span>Optional</span>
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
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}

          <div className="form-actions">
            <button className="secondary-button" type="button" disabled={busy} onClick={() => navigate("/applications")}>
              Cancel
            </button>
            <button
              className="primary-button"
              type="submit"
              disabled={busy || !name.trim()}
            >
              {busy ? (
                <>
                  <Spinner /> Creating…
                </>
              ) : (
                "Create application"
              )}
            </button>
          </div>
        </form>

        <aside className="info-card">
          <h2>Application boundary</h2>
          <p>
            An application organizes the targets, test runs, and authorized execution scopes for a single product area.
          </p>
          <p style={{ marginTop: "12px" }}>
            After creating this container, you will register target URLs (such as staging or QA environments) and explicitly authorize browser agents to test them.
          </p>
        </aside>
      </div>
    </>
  );
}

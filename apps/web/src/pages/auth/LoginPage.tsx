import { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowRight, Route, ScanLine, ShieldCheck } from "lucide-react";
import { Spinner } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { ApiError, CurrentUser, api } from "../../lib/api";
import { Link } from "react-router-dom";
import { PublicLayout } from "../public/PublicLayout";

export function LoginPage({
  onAuthenticated,
}: {
  onAuthenticated: (user: CurrentUser) => void;
}) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    document.title = "Sign in · MarketTwin";
    inputRef.current?.focus();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      const user = await api.login(email.trim());
      onAuthenticated(user);
    } catch (loginError) {
      const message =
        loginError instanceof ApiError && loginError.status >= 500
          ? "The login service is unavailable. Please try again when your workspace service is running."
          : loginError instanceof Error
          ? loginError.message
          : "Unable to sign in. Please try again.";
      setError(message);
      setTimeout(() => {
        errorRef.current?.focus();
      }, 50);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <PublicLayout title="Sign in">
    <div className="signin-page">
      {/* Informative Story Pane */}
      <section className="signin-story" aria-labelledby="signin-title">
        <div className="signin-story-content">
          <p className="signin-kicker">Evidence-Backed Product Testing</p>
          <h1 id="signin-title">
            Test user journeys.<br />
            <span>Review the evidence.</span>
          </h1>
          <p className="signin-description">
            Test your app with simulated testers and planned feature checks.
            Review recorded browser actions and the evidence available for each check.
          </p>

          <ol className="signin-workflow" aria-label="Core testing capabilities">
            <li>
              <span className="signin-step-icon">
                <ShieldCheck size={20} aria-hidden="true" />
              </span>
              <div>
                <strong>Authorized targets</strong>
                <p>Choose the target and network destinations your tests may access.</p>
              </div>
            </li>
            <li>
              <span className="signin-step-icon">
                <Route size={20} aria-hidden="true" />
              </span>
              <div>
                <strong>Watch live</strong>
                <p>Follow browser activity and review the steps recorded for your test.</p>
              </div>
            </li>
            <li>
              <span className="signin-step-icon">
                <ScanLine size={20} aria-hidden="true" />
              </span>
              <div>
                <strong>Review the evidence</strong>
                <p>See which issues have supporting evidence and which checks could not finish.</p>
              </div>
            </li>
          </ol>
        </div>

        <p className="signin-story-footer">
          MarketTwin Local Workspace Environment
        </p>
      </section>

      {/* Access Authentication Pane */}
      <section className="signin-access" aria-labelledby="signin-form-title">
        <p className="signin-mode">Local workspace authentication</p>

        <div className="signin-form-wrap">
          <p className="signin-kicker">Workspace Sign In</p>
          <h2 id="signin-form-title">Sign in to MarketTwin</h2>
          <p className="signin-form-description">
            Enter your approved workspace email address to access tests, live browser activity,
            and Test results.
          </p>

          <form onSubmit={submit} className="signin-form" aria-busy={busy}>
            <label htmlFor="email" className="signin-label">
              Work Email
            </label>
            <Input
              id="email"
              ref={inputRef}
              type="email"
              inputMode="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                if (error) setError(null);
              }}
              placeholder="name@company.com"
              autoComplete="email"
              autoCapitalize="none"
              spellCheck={false}
              required
              autoFocus
              aria-describedby={error ? "signin-help signin-error" : "signin-help"}
              className="signin-input"
            />
            <p id="signin-help" className="signin-help">
              Use the email address authorized for your local workspace.
            </p>

            {/* Reserved Error Container prevents Cumulative Layout Shift (CLS) */}
            <div className="signin-error-slot" aria-live="assertive">
              {error ? (
                <p
                  id="signin-error"
                  ref={errorRef}
                  tabIndex={-1}
                  className="form-error"
                  role="alert"
                >
                  {error}
                </p>
              ) : null}
            </div>

            <Button
              type="submit"
              disabled={busy || !email.trim()}
              className="signin-submit-btn"
            >
              {busy ? (
                <>
                  <Spinner />
                  <span>Signing in…</span>
                </>
              ) : (
                <>
                  <span>Continue to workspace</span>
                  <ArrowRight size={18} aria-hidden="true" />
                </>
              )}
            </Button>
          </form>

          <p className="signin-access-note">
            Need access? Ask your workspace administrator to add your email address to the authorized users list.
          </p>
        </div>

        <footer className="signin-access-footer">
          <Link to="/how-it-works">How MarketTwin works</Link>
          <span aria-hidden="true"> · </span>
          <Link to="/">Return to home</Link>
        </footer>
      </section>
    </div>
    </PublicLayout>
  );
}

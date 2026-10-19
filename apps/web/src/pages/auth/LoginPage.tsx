import { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowRight, Route, ScanLine, ShieldCheck } from "lucide-react";
import { BrandMark } from "../../components/ui/BrandMark";
import { Spinner } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { ApiError, CurrentUser, api } from "../../lib/api";
import { Link } from "react-router-dom";

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
    <main className="signin-page evidence-ledger-theme">
      {/* Informative Story Pane */}
      <section className="signin-story" aria-labelledby="signin-title">
        <Link className="signin-brand" to="/" aria-label="MarketTwin home">
          <BrandMark />
          <span>MarketTwin</span>
        </Link>
        <div className="signin-story-content">
          <p className="signin-kicker">Evidence-Backed Product Testing</p>
          <h1 id="signin-title">
            Test user journeys.<br />
            <span>Review the evidence.</span>
          </h1>
          <p className="signin-description">
            Run sandboxed browser tests with simulated personas and deterministic feature checks.
            Inspect every step alongside verifiable screenshots, network payloads, and execution logs.
          </p>

          <ol className="signin-workflow" aria-label="Core testing capabilities">
            <li>
              <span className="signin-step-icon">
                <ShieldCheck size={20} aria-hidden="true" />
              </span>
              <div>
                <strong>Authorized Target Scope</strong>
                <p>Browsers test strictly against permitted hostnames and approved network policies.</p>
              </div>
            </li>
            <li>
              <span className="signin-step-icon">
                <Route size={20} aria-hidden="true" />
              </span>
              <div>
                <strong>Observable Execution</strong>
                <p>Follow live step replays with captured DOM mutations, console output, and network timing.</p>
              </div>
            </li>
            <li>
              <span className="signin-step-icon">
                <ScanLine size={20} aria-hidden="true" />
              </span>
              <div>
                <strong>Evidence-First Triage</strong>
                <p>Verified defects are clearly isolated from inconclusive observations and runner limits.</p>
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
        <div className="signin-mode" aria-label="Workspace mode">
          <span className="signin-mode-dot" aria-hidden="true" />
          Local workspace authentication
        </div>

        <div className="signin-form-wrap">
          <p className="signin-kicker">Workspace Sign In</p>
          <h2 id="signin-form-title">Sign in to MarketTwin</h2>
          <p className="signin-form-description">
            Enter your approved workspace email address to access test runs, live browser observation,
            and the Evidence Ledger.
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
    </main>
  );
}

import { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowRight, ScanLine, Route, FileCheck2 } from "lucide-react";
import { BrandMark } from "../../components/ui/BrandMark";
import { Spinner } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { CurrentUser, api } from "../../lib/api";

export function LoginPage({
  onAuthenticated,
}: {
  onAuthenticated: (user: CurrentUser) => void;
}) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  useEffect(() => {
    document.title = "Sign in · MarketTwin";
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      onAuthenticated(await api.login(email.trim()));
    } catch (loginError) {
      setError(
        loginError instanceof Error
          ? loginError.message
          : "Unable to sign in. Please try again.",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <main className="signin-page">
      <section className="signin-story" aria-labelledby="signin-title">
        <div className="signin-brand">
          <BrandMark />
          <span>MarketTwin</span>
        </div>
        <div className="signin-story-content">
          <p className="signin-kicker">Product readiness testing</p>
          <h1 id="signin-title">
            Test user journeys.
            <br />
            <span>Review the evidence.</span>
          </h1>
          <p className="signin-description">
            Run browser tests with simulated users, inspect their journeys,
            and review findings alongside screenshots and logs.
          </p>
          <ol className="signin-workflow" aria-label="How MarketTwin works">
            <li>
              <span className="signin-step-icon">
                <ScanLine size={20} aria-hidden="true" />
              </span>
              <div>
                <strong>Define a task</strong>
                <p>Choose a target and describe the testing goal.</p>
              </div>
            </li>
            <li>
              <span className="signin-step-icon">
                <Route size={20} aria-hidden="true" />
              </span>
              <div>
                <strong>Run the test</strong>
                <p>Follow progress as simulated users explore the application.</p>
              </div>
            </li>
            <li>
              <span className="signin-step-icon">
                <FileCheck2 size={20} aria-hidden="true" />
              </span>
              <div>
                <strong>Review what happened</strong>
                <p>Connect findings to their supporting evidence.</p>
              </div>
            </li>
          </ol>
        </div>
        <p className="signin-story-footer">
          MarketTwin testing workspace
        </p>
      </section>
      <section className="signin-access" aria-labelledby="signin-form-title">
        <div className="signin-mode">
          <span aria-hidden="true" />
          Local workspace
        </div>
        <div className="signin-form-wrap">
          <h2 id="signin-form-title">Sign in to MarketTwin</h2>
          <p className="signin-form-description">
            Sign in to your workspace to create tests and review findings.
          </p>
          <form onSubmit={submit} className="signin-form" aria-busy={busy}>
            <label htmlFor="email">Email</label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                setError(null);
              }}
              placeholder="you@company.com"
              autoComplete="email"
              autoCapitalize="none"
              spellCheck={false}
              required
              aria-describedby={
                error ? "signin-help signin-error" : "signin-help"
              }
            />
            <p id="signin-help" className="signin-help">
              Use the email approved for this local workspace.
            </p>
            {error ? (
              <p id="signin-error" className="form-error" role="alert">
                {error}
              </p>
            ) : null}
            <Button type="submit" disabled={busy || !email.trim()}>
              {busy ? (
                <>
                  <Spinner />
                  Signing in
                </>
              ) : (
                <>
                  Continue
                  <ArrowRight size={18} aria-hidden="true" />
                </>
              )}
            </Button>
          </form>
          <p className="signin-access-note">
            Need access? Ask your workspace administrator to add your email.
          </p>
        </div>
        <footer className="signin-access-footer">
          Use an account approved by your workspace administrator.
        </footer>
      </section>
    </main>
  );
}

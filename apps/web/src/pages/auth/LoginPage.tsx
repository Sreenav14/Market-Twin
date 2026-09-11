import { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowRight, ScanLine, Route, FileCheck2 } from "lucide-react";
import { BrandMark } from "../../components/ui/BrandMark";
import { Spinner } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { CurrentUser, api } from "../../lib/api";

export function LoginPage({ onAuthenticated }: { onAuthenticated: (user: CurrentUser) => void }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  useEffect(() => { document.title = "Sign in · MarketTwin"; }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true); setError(null);
    try { onAuthenticated(await api.login(email.trim())); }
    catch (loginError) { setError(loginError instanceof Error ? loginError.message : "Unable to sign in. Please try again."); }
    finally { submitting.current = false; setBusy(false); }
  }
  return <main className="signin-page">
    <section className="signin-story" aria-labelledby="signin-title">
      <div className="signin-brand"><BrandMark /><span>MarketTwin</span></div>
      <div className="signin-story-content">
        <p className="signin-kicker">Product readiness testing</p>
        <h1 id="signin-title">Build an app<br /><span>people want to use.</span></h1>
        <p className="signin-description">Test your app with simulated users. Find usability barriers, uncover friction, and see whether its value comes through.</p>
        <ol className="signin-workflow" aria-label="How MarketTwin works">
          <li><span className="signin-step-icon"><ScanLine size={20} aria-hidden="true" /></span><div><strong>Put your app to the test</strong><p>Choose the experience you want to validate.</p></div></li>
          <li><span className="signin-step-icon"><Route size={20} aria-hidden="true" /></span><div><strong>Explore the experience</strong><p>Follow independent simulated user journeys.</p></div></li>
          <li><span className="signin-step-icon"><FileCheck2 size={20} aria-hidden="true" /></span><div><strong>Review what happened</strong><p>Connect findings to their supporting evidence.</p></div></li>
        </ol>
      </div>
      <p className="signin-story-footer">Find the friction before your users do.</p>
    </section>
    <section className="signin-access" aria-labelledby="signin-form-title">
      <div className="signin-mode"><span aria-hidden="true" />Local workspace</div>
      <div className="signin-form-wrap">
        <p className="signin-kicker">Put your product to the test</p>
        <h2 id="signin-form-title">Welcome to MarketTwin</h2>
        <p className="signin-form-description">Sign in to your workspace to create tests and review findings.</p>
        <form onSubmit={submit} className="signin-form" aria-busy={busy}>
          <label htmlFor="email">Email</label>
          <Input id="email" type="email" value={email} onChange={event => { setEmail(event.target.value); setError(null); }} placeholder="you@company.com" autoComplete="email" autoCapitalize="none" spellCheck={false} required aria-describedby={error ? "signin-help signin-error" : "signin-help"} />
          <p id="signin-help" className="signin-help">Use the email approved for this local workspace.</p>
          {error ? <p id="signin-error" className="form-error" role="alert">{error}</p> : null}
          <Button type="submit" disabled={busy || !email.trim()}>{busy ? <><Spinner />Signing in</> : <>Continue<ArrowRight size={18} aria-hidden="true" /></>}</Button>
        </form>
        <p className="signin-access-note">Need access? Ask your workspace administrator to add your email.</p>
      </div>
      <footer className="signin-access-footer">Authorized targets. Independent perspectives. Traceable findings.</footer>
    </section>
  </main>;
}

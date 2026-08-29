import { FormEvent, useEffect, useState } from "react";

import { BrandMark } from "../../components/ui/BrandMark";
import { Spinner } from "../../components/ui/StateViews";
import { CurrentUser, api } from "../../lib/api";

export function LoginPage({ onAuthenticated }: { onAuthenticated: (user: CurrentUser) => void }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { document.title = "Sign in · MarketTwin"; }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    try { onAuthenticated(await api.login(email.trim())); }
    catch (loginError) { setError(loginError instanceof Error ? loginError.message : "Login failed."); }
    finally { setBusy(false); }
  }

  return (
    <div className="auth-layout">
      <header className="auth-header"><div className="auth-brand"><BrandMark /><span>MarketTwin</span></div><span className="auth-environment">Local development</span></header>
      <main className="auth-main">
        <section className="auth-intro" aria-labelledby="auth-title"><p className="eyebrow">Product preflight</p><h1 id="auth-title">Test the experience before customers do.</h1><p>Run authorized browser studies from independent user perspectives and keep the resulting evidence in one workspace.</p><div className="auth-flow" aria-label="MarketTwin workflow"><span>Target</span><b>→</b><span>Study</span><b>→</b><span>Evidence</span></div></section>
        <section className="auth-card" aria-label="Sign in"><div className="auth-copy"><h2>Sign in</h2><p>Use a pre-approved local identity to open your workspace.</p></div><form onSubmit={submit} className="form-grid"><label className="field-label" htmlFor="email">Email</label><input id="email" className="text-input" type="email" value={email} onChange={(event) => { setEmail(event.target.value); setError(null); }} placeholder="you@company.com" autoComplete="email" required />{error ? <p className="form-error" role="alert">{error}</p> : null}<button className="primary-button full-width" type="submit" disabled={busy || !email.trim()}>{busy ? <><Spinner /> Signing in</> : "Continue"}</button></form></section>
      </main>
      <footer className="auth-footer">Authorized targets · Independent journeys · Evidence-backed findings</footer>
    </div>
  );
}

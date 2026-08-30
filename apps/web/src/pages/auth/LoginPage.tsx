import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Spinner } from "../../components/ui/StateViews";
import { CurrentUser, api } from "../../lib/api";
import { AuthFrame } from "./AuthFrame";

export function LoginPage({ onAuthenticated }: { onAuthenticated: (user: CurrentUser) => void }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { document.title = "Sign in · MarketTwin"; }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    try {
      onAuthenticated(await api.login(email.trim()));
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <div className="access-panel-header">
        <p className="access-panel-kicker">Workspace access</p>
        <h2>Sign in</h2>
        <p>Use your approved work identity to continue to MarketTwin.</p>
      </div>

      <form onSubmit={submit} className="access-form">
        <div className="access-field">
          <label htmlFor="email">Work email</label>
          <input
            id="email"
            className="text-input access-input"
            type="email"
            value={email}
            onChange={(event) => { setEmail(event.target.value); setError(null); }}
            placeholder="name@company.com"
            autoComplete="email"
            inputMode="email"
            required
          />
        </div>

        {error ? <p className="form-error" role="alert">{error}</p> : null}

        <button className="primary-button full-width access-submit" type="submit" disabled={busy || !email.trim()}>
          {busy ? <><Spinner /> Signing in</> : "Continue"}
        </button>
      </form>

      <div className="access-divider" aria-hidden="true"><span>New to MarketTwin?</span></div>

      <Link className="secondary-button full-width access-secondary" to="/signup">
        Create an account
      </Link>

      <p className="access-smallprint">
        Local development accepts only pre-provisioned identities. Production account creation will use the MarketTwin identity flow.
      </p>
    </AuthFrame>
  );
}

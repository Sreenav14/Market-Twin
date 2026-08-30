import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { AuthFrame } from "./AuthFrame";

export function SignupPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => { document.title = "Create account · MarketTwin"; }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
  }

  return (
    <AuthFrame>
      <div className="access-panel-header">
        <p className="access-panel-kicker">New workspace access</p>
        <h2>Create an account</h2>
        <p>Use your work email. Production signup will create or join the right MarketTwin workspace after identity verification.</p>
      </div>

      <form onSubmit={submit} className="access-form">
        <div className="access-field">
          <label htmlFor="signup-email">Work email</label>
          <input
            id="signup-email"
            className="text-input access-input"
            type="email"
            value={email}
            onChange={(event) => { setEmail(event.target.value); setSubmitted(false); }}
            placeholder="name@company.com"
            autoComplete="email"
            inputMode="email"
            required
          />
        </div>

        <button className="primary-button full-width access-submit" type="submit" disabled={!email.trim()}>
          Continue
        </button>
      </form>

      {submitted ? (
        <div className="access-notice" role="status">
          <strong>Account creation is not enabled in local development.</strong>
          <p>
            This route reserves the production signup experience. The production backend will use Cognito verification and MarketTwin workspace provisioning rather than creating a frontend-only account.
          </p>
        </div>
      ) : (
        <div className="access-notice subtle">
          <strong>Production flow</strong>
          <p>Email verification, invitation-aware workspace joining, and recovery flows will activate when the Cognito/BFF authentication contract is implemented.</p>
        </div>
      )}

      <div className="access-divider" aria-hidden="true"><span>Already have access?</span></div>
      <Link className="secondary-button full-width access-secondary" to="/login">Sign in instead</Link>

      <p className="access-smallprint">
        MarketTwin account authentication is separate from login, MFA, CAPTCHA, or signup steps inside a website being tested.
      </p>
    </AuthFrame>
  );
}

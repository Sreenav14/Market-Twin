import { Link } from "react-router-dom";
import { PublicLayout } from "../public/PublicLayout";

export function AuthCallbackPage() {
  return (
    <PublicLayout title="Authentication">
      <section className="concept-system" aria-labelledby="auth-callback-title">
        <div className="concept-system-content">
          <p className="font-meta-label">Production authentication</p>
          <h1 id="auth-callback-title">Production sign-in is not available here</h1>
          <p>
            This workspace uses local sign-in. Production Cognito authentication
            is not configured on this page, and this callback does not sign you in.
          </p>
          <Link className="concept-public-primary" to="/login">Return to sign in</Link>
        </div>
      </section>
    </PublicLayout>
  );
}

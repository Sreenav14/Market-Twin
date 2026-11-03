import { Link } from "react-router-dom";
import { ShieldAlert, Home } from "lucide-react";

export function ForbiddenPage() {
  return (
    <section className="concept-system" aria-labelledby="system-page-title">
      <div className="concept-system-content">
        <ShieldAlert className="concept-system-icon" size={24} aria-hidden="true" />
        <h1 id="system-page-title">Access restricted</h1>
        <p>You do not have permission to view this resource or perform this action. Permissions in MarketTwin are enforced by the server according to your workspace role.</p>
        <div className="concept-system-actions">
          <Link to="/dashboard" className="primary-button">
            <Home size={15} aria-hidden="true" />
            <span>Return to Dashboard</span>
          </Link>
          <Link to="/runs" className="secondary-button">See tests</Link>
        </div>
      </div>
    </section>
  );
}

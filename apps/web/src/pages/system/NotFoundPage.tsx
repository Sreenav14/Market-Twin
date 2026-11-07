import { Link } from "react-router-dom";
import { Compass, Home } from "lucide-react";

export function NotFoundPage() {
  return (
    <section className="concept-system" aria-labelledby="system-page-title">
      <div className="concept-system-content">
        <Compass className="concept-system-icon" size={24} aria-hidden="true" />
        <h1 id="system-page-title">Page unavailable</h1>
        <p>The requested page or resource could not be found. It may have moved, been archived, or may not exist in your active workspace.</p>
        <div className="concept-system-actions">
          <Link to="/dashboard" className="primary-button">
            <Home size={15} aria-hidden="true" />
            <span>Return to Home</span>
          </Link>
          <Link to="/runs" className="secondary-button">See tests</Link>
        </div>
      </div>
    </section>
  );
}

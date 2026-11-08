import { Link } from "react-router-dom";
import { AlertCircle, Home, RotateCcw } from "lucide-react";
import { Button } from "../../components/ui/button";

export function UnexpectedErrorPage() {
  return (
    <section className="concept-system" aria-labelledby="system-page-title">
      <div className="concept-system-content">
        <AlertCircle className="concept-system-icon" size={24} aria-hidden="true" />
        <h1 id="system-page-title">Something unexpected occurred</h1>
        <p>MarketTwin encountered an issue while displaying this view. Reload the page to try again. If the problem continues, return to Home.</p>
        <div className="concept-system-actions">
          <Link to="/dashboard" className="primary-button">
            <Home size={16} aria-hidden="true" />
            <span>Return to Home</span>
          </Link>
          <Button variant="secondary" onClick={() => window.location.reload()}>
            <RotateCcw size={16} aria-hidden="true" />
            <span>Reload page</span>
          </Button>
        </div>
      </div>
    </section>
  );
}

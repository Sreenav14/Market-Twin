import { useEffect, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ConceptFooter } from "../../components/concept/ConceptFooter";

export function PublicLayout({ title, children }: { title: string; children: ReactNode }) {
  const navigate = useNavigate();
  useEffect(() => {
    document.title = `${title} · MarketTwin`;
    if (!window.location.hash) window.scrollTo({ top: 0 });
  }, [title]);

  const destinations: Record<string, string> = {
    "Landing page": "/", Dashboard: "/dashboard", "Watch live": "/dashboard",
    "Test results": "/runs", Testers: "/agents", "Example report": "/examples/results",
    "How it works": "/how-it-works", "Your apps": "/applications",
    "Add an app": "/applications/new", Settings: "/settings",
  };

  return (
    <div className="concept-public">
      <a className="concept-public-skip" href="#public-content">Skip to content</a>
      <header className="concept-public-header">
        <Link className="concept-public-brand" to="/" aria-label="MarketTwin home">MarketTwin</Link>
        <nav aria-label="Product navigation">
          <Link to="/how-it-works">How it works</Link>
          <Link to="/login">Sign in</Link>
          <Link className="concept-public-primary" to="/applications/new">Start a test</Link>
        </nav>
      </header>
      <main id="public-content" tabIndex={-1}>{children}</main>
      <ConceptFooter onNavigate={(destination) => {
        const path = destinations[destination];
        if (path) navigate(path);
      }} />
    </div>
  );
}

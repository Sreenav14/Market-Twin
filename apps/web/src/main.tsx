import { FormEvent, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";

import "./styles.css";

type NavigationItem = "Home" | "Runs" | "Settings";

function MarkIcon() {
  return (
    <svg viewBox="0 0 28 28" aria-hidden="true" className="mark-icon">
      <rect x="2" y="2" width="24" height="24" rx="8" />
      <path d="M8 17.5 12.1 9l3.2 6 2.3-4.5L20 17.5" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="button-icon">
      <path d="M4 10h11M11 6l4 4-4 4" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="chevron-icon">
      <path d="m7.5 5 5 5-5 5" />
    </svg>
  );
}

function App() {
  const [activeNavigation, setActiveNavigation] = useState<NavigationItem>("Home");
  const [website, setWebsite] = useState("http://localhost:3000/");
  const [studyBrief, setStudyBrief] = useState("");
  const [showDetails, setShowDetails] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const canRun = useMemo(
    () => website.trim().length > 0 && studyBrief.trim().length >= 10,
    [studyBrief, website],
  );

  function submitStudy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!canRun) {
      return;
    }

    setSubmitted(true);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-row">
          <MarkIcon />
          <span className="brand-name">MarketTwin</span>
        </div>

        <nav className="nav-list">
          {(["Home", "Runs", "Settings"] as const).map((item) => (
            <button
              className={`nav-item ${activeNavigation === item ? "is-active" : ""}`}
              key={item}
              onClick={() => setActiveNavigation(item)}
              type="button"
            >
              <span>{item}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="account-avatar" aria-hidden="true">
            S
          </div>
          <div className="account-copy">
            <span className="account-name">Local workspace</span>
            <span className="account-detail">Development</span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">New study</p>
          </div>
          <div className="status-pill">
            <span className="status-dot" />
            Local environment
          </div>
        </header>

        <section className="hero-section">
          <p className="hero-kicker">See your product through different users.</p>
          <h1>What do you want to learn?</h1>
          <p className="hero-copy">
            Give MarketTwin one goal. It will prepare relevant user perspectives,
            test the experience independently, and surface where the experience breaks down.
          </p>
        </section>

        <form className="study-card" onSubmit={submitStudy}>
          <div className="field-group compact-field">
            <label htmlFor="website">Website</label>
            <div className="input-shell">
              <span className="site-indicator" aria-hidden="true" />
              <input
                id="website"
                value={website}
                onChange={(event) => {
                  setWebsite(event.target.value);
                  setSubmitted(false);
                }}
                inputMode="url"
                autoComplete="url"
                spellCheck={false}
                aria-describedby="website-hint"
              />
              <span className="verified-label">Authorized</span>
            </div>
            <span id="website-hint" className="sr-only">
              Enter the authorized website you want MarketTwin to evaluate.
            </span>
          </div>

          <div className="divider" />

          <div className="field-group">
            <label htmlFor="study-brief">Testing goal</label>
            <textarea
              id="study-brief"
              value={studyBrief}
              onChange={(event) => {
                setStudyBrief(event.target.value);
                setSubmitted(false);
              }}
              placeholder="For example: Check whether first-time customers can understand our pricing and confidently choose the right plan."
              rows={5}
              maxLength={4000}
            />
            <div className="field-meta">
              <span>Describe the outcome you care about, not the test steps.</span>
              <span>{studyBrief.length}/4000</span>
            </div>
          </div>

          <button
            type="button"
            className="disclosure-button"
            aria-expanded={showDetails}
            onClick={() => setShowDetails((current) => !current)}
          >
            <span>Study details</span>
            <span className={showDetails ? "chevron-rotate" : ""}>
              <ChevronIcon />
            </span>
          </button>

          {showDetails && (
            <div className="details-panel">
              <div>
                <span className="detail-label">Environment</span>
                <strong>Local development</strong>
              </div>
              <div>
                <span className="detail-label">User perspectives</span>
                <strong>Generated dynamically</strong>
              </div>
              <div>
                <span className="detail-label">Browser</span>
                <strong>Isolated Chromium sessions</strong>
              </div>
            </div>
          )}

          <div className="card-footer">
            <div className="privacy-note">
              <span className="privacy-symbol" aria-hidden="true">✓</span>
              <span>MarketTwin only tests the website you authorize.</span>
            </div>
            <button className="primary-button" type="submit" disabled={!canRun}>
              <span>Run study</span>
              <ArrowIcon />
            </button>
          </div>
        </form>

        {submitted && (
          <section className="confirmation-card" aria-live="polite">
            <div className="confirmation-icon" aria-hidden="true">✓</div>
            <div>
              <p className="confirmation-title">Study is ready to start</p>
              <p className="confirmation-copy">
                The interface is prepared. Backend planning will be connected in the next implementation step.
              </p>
            </div>
          </section>
        )}

        <section className="recent-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">History</p>
              <h2>Recent studies</h2>
            </div>
          </div>

          <div className="empty-state">
            <div className="empty-art" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <p className="empty-title">Your studies will appear here.</p>
            <p className="empty-copy">
              Run your first study above to start building a history of product insights.
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}

const rootElement = document.getElementById("root");

if (rootElement === null) {
  throw new Error("MarketTwin root element was not found.");
}

createRoot(rootElement).render(<App />);

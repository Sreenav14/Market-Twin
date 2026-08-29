import { FormEvent, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";

import "./styles.css";

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect x="2" y="2" width="28" height="28" rx="9" />
      <path d="M9 20 13.1 11l3.4 6.4 2.5-4.7L23 20" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg className="button-icon" viewBox="0 0 20 20" aria-hidden="true">
      <path d="M4 10h11M11 6l4 4-4 4" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg className="chevron-icon" viewBox="0 0 20 20" aria-hidden="true">
      <path d="m7.5 5 5 5-5 5" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="check-icon" viewBox="0 0 20 20" aria-hidden="true">
      <path d="m5 10.2 3.1 3.1L15 6.8" />
    </svg>
  );
}

function App() {
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
      <header className="app-header">
        <div className="header-inner">
          <a className="brand" href="#main" aria-label="MarketTwin home">
            <BrandMark />
            <span>MarketTwin</span>
          </a>

          <div className="header-context" aria-label="Current environment">
            <span className="environment-dot" />
            <span>Local workspace</span>
          </div>
        </div>
      </header>

      <main id="main" className="main-content">
        <section className="intro" aria-labelledby="page-title">
          <p className="eyebrow">New study</p>
          <h1 id="page-title">What do you want to learn?</h1>
          <p className="intro-copy">
            Give MarketTwin a product goal. It prepares relevant user perspectives,
            tests the experience independently, and surfaces where people may struggle.
          </p>
        </section>

        <form className="study-card" onSubmit={submitStudy} noValidate>
          <div className="card-section">
            <div className="section-label-row">
              <label htmlFor="website">Website</label>
              <span className="field-status">
                <span className="field-status-dot" />
                Local target
              </span>
            </div>

            <input
              id="website"
              className="url-input"
              type="url"
              value={website}
              onChange={(event) => {
                setWebsite(event.target.value);
                setSubmitted(false);
              }}
              autoComplete="url"
              inputMode="url"
              spellCheck={false}
              aria-describedby="website-help"
            />
            <p id="website-help" className="field-help">
              Choose a website you own or are authorized to test.
            </p>
          </div>

          <div className="card-divider" />

          <div className="card-section goal-section">
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
              aria-describedby="study-help study-count"
            />
            <div className="field-meta">
              <span id="study-help">Describe the outcome you care about, not the test steps.</span>
              <span id="study-count" aria-live="polite">
                {studyBrief.length}/4000
              </span>
            </div>
          </div>

          <button
            type="button"
            className="details-trigger"
            aria-expanded={showDetails}
            aria-controls="study-details"
            onClick={() => setShowDetails((current) => !current)}
          >
            <span>How this study will run</span>
            <span className={showDetails ? "chevron-wrapper is-open" : "chevron-wrapper"}>
              <ChevronIcon />
            </span>
          </button>

          {showDetails && (
            <div id="study-details" className="details-panel">
              <div className="detail-item">
                <span className="detail-icon"><CheckIcon /></span>
                <div>
                  <strong>Relevant perspectives</strong>
                  <p>Generated dynamically from your goal and target.</p>
                </div>
              </div>
              <div className="detail-item">
                <span className="detail-icon"><CheckIcon /></span>
                <div>
                  <strong>Independent journeys</strong>
                  <p>Each perspective evaluates the experience separately.</p>
                </div>
              </div>
              <div className="detail-item">
                <span className="detail-icon"><CheckIcon /></span>
                <div>
                  <strong>Evidence-backed findings</strong>
                  <p>Results are tied to observable browser evidence.</p>
                </div>
              </div>
            </div>
          )}

          <div className="card-actions">
            <p className="authorization-note">
              MarketTwin tests only targets you authorize.
            </p>
            <button className="primary-button" type="submit" disabled={!canRun}>
              <span>Run study</span>
              <ArrowIcon />
            </button>
          </div>
        </form>

        {submitted && (
          <section className="prototype-notice" aria-live="polite">
            <span className="notice-icon"><CheckIcon /></span>
            <div>
              <strong>Study input is ready.</strong>
              <p>This branch is the product interface only; planning and execution are not simulated.</p>
            </div>
          </section>
        )}

        <section className="recent" aria-labelledby="recent-title">
          <div className="recent-heading">
            <div>
              <p className="eyebrow">History</p>
              <h2 id="recent-title">Recent studies</h2>
            </div>
          </div>

          <div className="empty-state">
            <div className="empty-symbol" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <div>
              <strong>No studies yet</strong>
              <p>Your completed and in-progress studies will appear here.</p>
            </div>
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

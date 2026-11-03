import { Link, Navigate } from "react-router-dom";
import { ArrowRight, Route, FileCheck2, ChevronDown } from "lucide-react";
import { PublicLayout } from "./PublicLayout";

export function HomePage() {
  return <Navigate to="/" replace />;
}

export function HowPage() {
  return (
    <PublicLayout title="How it works">
      {/* Header Section */}
      <section className="mt-how-hero" aria-labelledby="how-hero-heading">
        <p className="mt-kicker">How it works</p>
        <h1 id="how-hero-heading">
          A product question.<br />
          An authorized scope.<br />
          <em>An evidence trail.</em>
        </h1>
        <p className="mt-lead">
          Choose what to check, authorize the target, and review the recorded browser steps.
          Results show what the evidence supports and what still needs checking.
        </p>
        <nav className="mt-anchor-nav" aria-label="Section jump links">
          <a href="#setup">01 / Scope & Setup</a>
          <a href="#trace">02 / Recorded steps</a>
          <a href="#execution">03 / Ways to test</a>
          <a href="#results">04 / Test results</a>
          <a href="#inconclusive">05 / Missing checks</a>
          <a href="#limits">06 / Boundaries & Limits</a>
        </nav>
      </section>

      {/* Section 01: Setup & Scope */}
      <section className="mt-how-section" id="setup">
        <div className="mt-how-header">
          <p className="mt-kicker">01 / Setup</p>
          <h2>Give the test a clear, authorized purpose.</h2>
        </div>
        <div className="mt-how-body">
          <article>
            <h3>Connect an application and authorize a target</h3>
            <p>
              An application groups related testing work. A target defines the specific web environment
              to explore. Before any test can run, a workspace administrator must explicitly authorize the
              target URL and attest to testing permissions.
            </p>
          </article>

          <article>
            <h3>Choose allowed network destinations</h3>
            <p>
              Each target has a list of allowed network destinations. Browser requests outside that list
              are blocked. Include the destinations your app needs before starting the test.
            </p>
          </article>

          <article>
            <h3>Optional approved product knowledge</h3>
            <p>
              Teams may attach reviewed product specifications, OpenAPI schemas, or user documentation to an application.
              This helps plan checks for expected behavior. Documentation provides context;
              browser evidence is still needed to check the app.
            </p>
          </article>
        </div>
      </section>

      {/* Section 02: Trace Pipeline Flow */}
      <section className="mt-how-section" id="trace">
        <div className="mt-how-header">
          <p className="mt-kicker">02 / Recorded steps</p>
          <h2>From question to conclusion in five stages.</h2>
        </div>
        <div className="mt-how-body">
          <div className="mt-trace-pipeline" aria-label="Five-stage trace diagram">
            <div className="mt-trace-step">
              <span className="mt-trace-badge">1. Question</span>
              <h4>Define Intent</h4>
              <p>Formulate the test goal and explicit acceptance criteria (e.g. “Can a new user complete onboarding?”).</p>
            </div>
            <div className="mt-trace-arrow" aria-hidden="true">→</div>
            <div className="mt-trace-step">
              <span className="mt-trace-badge">2. Scope</span>
              <h4>Validate Policy</h4>
              <p>Verify authorized target hostnames, allowed network destinations, and execution depth settings.</p>
            </div>
            <div className="mt-trace-arrow" aria-hidden="true">→</div>
            <div className="mt-trace-step">
              <span className="mt-trace-badge">3. Browser</span>
              <h4>Execute Actions</h4>
              <p>Sandboxed browser performs structured navigation, clicks, and inputs within authorized bounds.</p>
            </div>
            <div className="mt-trace-arrow" aria-hidden="true">→</div>
            <div className="mt-trace-step">
              <span className="mt-trace-badge">4. Evidence</span>
              <h4>Capture Artifacts</h4>
              <p>Record timed screenshots, DOM snapshots, network payloads, and browser console messages.</p>
            </div>
            <div className="mt-trace-arrow" aria-hidden="true">→</div>
            <div className="mt-trace-step">
              <span className="mt-trace-badge">5. Conclusion</span>
              <h4>Classify Findings</h4>
              <p>Match recorded artifacts against criteria into Verified, Needs verification, or Execution issues.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Section 03: Current Execution Modes */}
      <section className="mt-how-section" id="execution">
        <div className="mt-how-header">
          <p className="mt-kicker">03 / Ways to test</p>
          <h2>Explore journeys or check specific features.</h2>
        </div>
        <div className="mt-how-body">
          <div className="mt-modes-grid">
            <article className="mt-mode-card">
              <div className="mt-mode-card-header">
                <Route size={20} aria-hidden="true" />
                <h3>Simulated testers</h3>
              </div>
              <p>
                Simulated testers explore your app from different perspectives, such as a first-time visitor
                or an experienced customer. The selected test depth sets how much they attempt.
              </p>
              <p className="mt-mode-note">
                <strong>Keep in mind:</strong> Simulated testers are software. Agreement between them
                is a reason to investigate, not independent proof of a defect.
              </p>
            </article>

            <article className="mt-mode-card">
              <div className="mt-mode-card-header">
                <FileCheck2 size={20} aria-hidden="true" />
                <h3>Feature checks</h3>
              </div>
              <p>
                Feature checks follow planned actions and compare observed behavior with the expected result.
                Review the proposed checks before approving browser activity.
              </p>
              <ul className="mt-mode-specs">
                <li>Planned browser actions, step by step</li>
                <li>Checks against page content and available network responses</li>
                <li>Results linked to the checks and available evidence</li>
              </ul>
              <p className="mt-mode-note">
                Review the recorded steps and available evidence before deciding what to fix.
              </p>
            </article>
          </div>
        </div>
      </section>

      {/* Section 04: Result Triage */}
      <section className="mt-how-section" id="results">
        <div className="mt-how-header">
          <p className="mt-kicker">04 / Test results</p>
          <h2>Know what each category proves.</h2>
        </div>
        <div className="mt-how-body">
          <div className="mt-how-result-group">
            <article className="mt-how-result">
              <span className="mt-result-marker mt-confirmed" aria-hidden="true" />
              <div>
                <h3>Confirmed issues</h3>
                <p>
                  Inspect the cited steps and available evidence before choosing a fix. An issue is labelled
                  Broken only when a repeat check also failed. A reported issue without that repeat evidence
                  still needs checking.
                </p>
              </div>
            </article>

            <article className="mt-how-result">
              <span className="mt-result-marker mt-unverified" aria-hidden="true" />
              <div>
                <h3>Needs checking</h3>
                <p>
                  Tester reports and unexpected stops may have partial or missing evidence. Repetition across
                  simulated testers does not confirm a defect. Review the supporting steps to decide what
                  needs another check.
                </p>
              </div>
            </article>

            <article className="mt-how-result">
              <span className="mt-result-marker mt-execution" aria-hidden="true" />
              <div>
                <h3>Could not check</h3>
                <p>
                  A failed browser action, timeout, or network policy block may prevent a check.
                  These limits do not establish whether the app works or is broken.
                </p>
              </div>
            </article>
          </div>

          <div className="mt-how-summary-note">
            <h4>Reading Test results</h4>
            <p>
              Start by reviewing the target scope and completed journeys, then investigate reported issues.
              Open the cited artifact links to view the actual screenshot. An empty findings list does not guarantee a
              defect-free product.
            </p>
          </div>
        </div>
      </section>

      {/* Section 05: Inconclusive Test Reasons */}
      <section className="mt-how-section" id="inconclusive">
        <div className="mt-how-header">
          <p className="mt-kicker">05 / Missing checks</p>
          <h2>Why some checks cannot finish.</h2>
        </div>
        <div className="mt-how-body">
          <p className="mt-how-body-lead">
            When a check cannot finish, review its recorded reason. A blocked or incomplete check
            does not by itself establish a product failure:
          </p>

          <div className="mt-disclosures" role="region" aria-label="Reasons checks cannot finish">
            <details>
              <summary>
                <span>Destination origin outside network policy</span>
                <ChevronDown size={18} aria-hidden="true" className="mt-disclosure-arrow" />
              </summary>
              <p>
                The browser attempted to navigate to an external URL or third-party resource (such as social login,
                CDN assets, or payment gateways) not included in the target's authorized origins. MarketTwin blocks
                unauthorized destinations by default to protect test boundaries.
              </p>
            </details>

            <details>
              <summary>
                <span>Authentication or MFA challenge encountered</span>
                <ChevronDown size={18} aria-hidden="true" className="mt-disclosure-arrow" />
              </summary>
              <p>
                The journey reached a login screen, SSO identity provider, CAPTCHA, or multi-factor prompt.
                Without pre-configured test credentials or Human-in-the-Loop intervention, the runner pauses or terminates
                the journey without a completed check.
              </p>
            </details>

            <details>
              <summary>
                <span>Dynamic DOM hydration or asynchronous loading delay</span>
                <ChevronDown size={18} aria-hidden="true" className="mt-disclosure-arrow" />
              </summary>
              <p>
                Single-page web applications may load elements asynchronously. If an interactive selector fails to
                mount before the step timeout expires, MarketTwin records the actual DOM state and marks the step timed out
                rather than guessing an interaction.
              </p>
            </details>

            <details>
              <summary>
                <span>Missing or uncaptured artifact</span>
                <ChevronDown size={18} aria-hidden="true" className="mt-disclosure-arrow" />
              </summary>
              <p>
                If a screenshot capture fails due to rapid page unmounting, MarketTwin marks the step as
                “Evidence unavailable.” Adjacent screenshots are never substituted for the missing evidence.
              </p>
            </details>

            <details>
              <summary>
                <span>Tester did not finish the task</span>
                <ChevronDown size={18} aria-hidden="true" className="mt-disclosure-arrow" />
              </summary>
              <p>
                A simulated tester may follow other links or reach its step limit before finishing the task.
                Review the recorded actions; unfinished work still needs checking.
              </p>
            </details>

            <details>
              <summary>
                <span>Evaluator queue backlog or worker timeout</span>
                <ChevronDown size={18} aria-hidden="true" className="mt-disclosure-arrow" />
              </summary>
              <p>
                Browser execution and automated evaluation are separate processes. If evaluation is queued or the evaluator
                worker experiences latency, the test may remain waiting for its results.
              </p>
            </details>
          </div>
        </div>
      </section>

      {/* Section 06: Boundaries & Limits */}
      <section className="mt-how-section" id="limits">
        <div className="mt-how-header">
          <p className="mt-kicker">06 / Honest Boundaries</p>
          <h2>Useful evidence. Transparent limits.</h2>
        </div>
        <div className="mt-how-body">
          <article>
            <h3>Help a tester</h3>
            <p>
              When a supported test encounters CAPTCHA, payment authorization, or sensitive identity verification,
              it pauses and requests human intervention. A designated operator can lease the live browser session,
              complete the requested action, and hand control back. Follow the available controls and check the result.
            </p>
          </article>

          <article>
            <h3>System Boundaries & Responsible Use</h3>
            <p>
              Simulated journeys complement human engineering and quality assurance; they do not measure real human sentiment,
              market preferences, or usability satisfaction. MarketTwin does not replace accessibility (WCAG) certification
              or penetration security auditing.
            </p>
          </article>

          <article>
            <h3>Authorized Workspace Access</h3>
            <p>
              MarketTwin operates with local workspace authentication. Use an approved email address to sign in. Your workspace role controls which actions
              you can take, including starting tests and changing network policies.
            </p>
          </article>
        </div>
      </section>

      {/* Closing Action */}
      <section className="mt-closing" aria-labelledby="how-closing-heading">
        <h2 id="how-closing-heading">Ready to inspect a browser journey?</h2>
        <div className="mt-actions-center">
          <Link className="mt-button" to="/login">
            Sign in <ArrowRight size={18} aria-hidden="true" />
          </Link>
          <Link className="mt-text-link" to="/">
            Back to home
          </Link>
        </div>
      </section>
    </PublicLayout>
  );
}

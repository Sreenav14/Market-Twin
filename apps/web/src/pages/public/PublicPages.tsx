import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Route,
  ScanLine,
  ShieldCheck,
  Layers,
  FileCheck2,
  Lock,
  ChevronDown,
} from "lucide-react";
import { BrandMark } from "../../components/ui/BrandMark";

function PublicLayout({ title, children }: { title: string; children: ReactNode }) {
  useEffect(() => {
    document.title = `${title} · MarketTwin`;
    if (!window.location.hash) window.scrollTo({ top: 0 });
  }, [title]);

  return (
    <div className="mt-public evidence-ledger-theme">
      <a className="mt-skip" href="#public-content">
        Skip to content
      </a>
      <header className="mt-nav">
        <Link className="mt-brand" to="/" aria-label="MarketTwin home">
          <BrandMark />
          <span>
            MarketTwin
            <span className="mt-brand-note">Product testing, with evidence.</span>
          </span>
        </Link>
        <nav aria-label="Product navigation">
          <NavLink to="/how-it-works">How it works</NavLink>
          <Link className="mt-button mt-button-small" to="/login">
            Open workspace <ArrowUpRight size={16} aria-hidden="true" />
          </Link>
        </nav>
      </header>
      <main id="public-content" tabIndex={-1}>
        {children}
      </main>
      <footer className="mt-footer">
        <div className="mt-footer-brand">
          <Link className="mt-brand" to="/" aria-label="MarketTwin home">
            <BrandMark compact />
            <span>MarketTwin</span>
          </Link>
          <p className="mt-footer-tagline">
            Authorized browser testing, observable execution, and verifiable evidence.
          </p>
        </div>
        <nav aria-label="Footer navigation">
          <Link to="/">Home</Link>
          <Link to="/how-it-works">How it works</Link>
          <Link to="/login">Open workspace</Link>
        </nav>
        <div className="mt-footer-legal">
          <p>
            MarketTwin executes against authorized targets only. Simulated persona observations
            are illustrative and do not replace human research.
          </p>
        </div>
      </footer>
    </div>
  );
}

interface EvidenceStep {
  stepNumber: string;
  action: string;
  targetUrl: string;
  observation: string;
  evidenceKind: string;
  evidenceId: string;
  statusText: string;
  criterion: string;
}

const illustrativeSteps: EvidenceStep[] = [
  {
    stepNumber: "01",
    action: "Load /pricing page",
    targetUrl: "https://app.example.com/pricing",
    observation: "Browser navigates to target. 3 subscription tiers and billing frequency toggle are rendered in the DOM.",
    evidenceKind: "Screenshot & DOM Snapshot",
    evidenceId: "art-01-pricing.png",
    statusText: "Verified in target scope",
    criterion: "Page loads with HTTP 200 within authorized target origin",
  },
  {
    stepNumber: "02",
    action: "Toggle annual billing switch",
    targetUrl: "https://app.example.com/pricing",
    observation: "User activates annual discount switch. Pricing cards recalculate prices to reflect 20% annual savings.",
    evidenceKind: "Visual State Diff & DOM Event",
    evidenceId: "art-02-toggle.png",
    statusText: "Verified in target scope",
    criterion: "Element [data-tier='pro'] updates price text from $49 to $39",
  },
  {
    stepNumber: "03",
    action: "Select Pro plan & open checkout",
    targetUrl: "https://app.example.com/checkout?plan=pro",
    observation: "Modal mounts with order summary. POST /api/checkout completes without policy violation or console error.",
    evidenceKind: "Network Payload & DOM Snapshot",
    evidenceId: "art-03-checkout.png",
    statusText: "Verified in target scope",
    criterion: "Checkout modal mounts with active session in approved origin",
  },
];

function HeroEvidenceSequence() {
  const [selected, setSelected] = useState(0);
  const step = illustrativeSteps[selected];

  return (
    <div className="mt-instrument" aria-labelledby="hero-evidence-title">
      <div className="mt-instrument-bar">
        <span id="hero-evidence-title">
          <span className="mt-light" aria-hidden="true" />
          Evidence Ledger Explorer
        </span>
        <span className="mt-badge-demo" aria-label="Illustrative demonstration label">
          Illustrative observation sequence
        </span>
      </div>

      <div className="mt-instrument-context">
        <div className="mt-question-callout">
          <span className="mt-kicker">Testing Question</span>
          <p className="mt-question-text">
            “Can a first-time customer compare plans, select annual billing, and reach checkout without network errors?”
          </p>
        </div>
        <div className="mt-target-tag">
          <span className="mt-kicker">Authorized target:</span>
          <code>https://app.example.com</code>
        </div>
      </div>

      <div className="mt-demo-grid">
        <ol className="mt-step-selector" aria-label="Illustrative test steps">
          {illustrativeSteps.map((item, index) => {
            const isSelected = index === selected;
            return (
              <li key={item.stepNumber}>
                <button
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => setSelected(index)}
                  className={isSelected ? "active" : ""}
                >
                  <span className="mt-step-number">{item.stepNumber}</span>
                  <span className="mt-step-action-name">{item.action}</span>
                  <ArrowRight size={14} aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ol>

        <div className="mt-demo-evidence" aria-live="polite">
          <div className="mt-mini-browser" aria-hidden="true">
            <div className="mt-mini-browser-bar">
              <span className="mt-mini-dot" />
              <span className="mt-mini-dot" />
              <span className="mt-mini-dot" />
              <span className="mt-mini-url">{step.targetUrl}</span>
            </div>
            <div className={`mt-mini-canvas mt-canvas-step-${selected + 1}`}>
              <div className="mt-canvas-header">
                <span className="mt-skeleton-pill" />
                <span className="mt-skeleton-line" />
              </div>
              <div className="mt-canvas-plans">
                <div className={`mt-plan-card ${selected >= 1 ? "active-plan" : ""}`} />
                <div className="mt-plan-card" />
              </div>
              <div className="mt-canvas-badge">
                <Check size={14} aria-hidden="true" />
                <span>Step {step.stepNumber} verified</span>
              </div>
            </div>
          </div>

          <div className="mt-evidence-card">
            <div className="mt-evidence-card-header">
              <span className="mt-kicker">Observation</span>
              <span className="mt-status-tag verified">
                <CheckCircle2 size={12} aria-hidden="true" /> {step.statusText}
              </span>
            </div>
            <p className="mt-observation-text">{step.observation}</p>

            <div className="mt-evidence-receipt">
              <div className="mt-receipt-row">
                <span className="mt-receipt-label">Evidence:</span>
                <span className="mt-receipt-value">{step.evidenceKind}</span>
              </div>
              <div className="mt-receipt-row">
                <span className="mt-receipt-label">Criterion:</span>
                <span className="mt-receipt-value">{step.criterion}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <p className="mt-example-note">
        Illustration only. Live workspaces record actual browser screenshots, DOM snapshots, network payloads, and signed artifacts.
      </p>
    </div>
  );
}

export function HomePage() {
  return (
    <PublicLayout title="Understand what your users encounter">
      {/* Hero Section */}
      <section className="mt-hero" aria-labelledby="hero-heading">
        <div className="mt-hero-copy">
          <p className="mt-kicker">
            <span className="mt-light" aria-hidden="true" />
            Authorized browser testing · Evidence-backed verification
          </p>
          <h1 id="hero-heading">
            From a product question<br />
            to verifiable<br />
            <em>browser evidence.</em>
          </h1>
          <p className="mt-lead">
            MarketTwin executes planned browser journeys and deterministic feature cases against
            authorized targets. Every click, network request, and visual state is captured into a
            verifiable Evidence Ledger.
          </p>

          <div className="mt-actions">
            <Link className="mt-button" to="/login">
              Open workspace <ArrowRight size={18} aria-hidden="true" />
            </Link>
            <Link className="mt-text-link" to="/how-it-works">
              See how it works <ArrowUpRight size={17} aria-hidden="true" />
            </Link>
          </div>

          <p className="mt-hero-footnote">
            <ShieldCheck size={16} aria-hidden="true" />
            Tests run strictly against targets and network origins you authorize.
          </p>
        </div>

        <HeroEvidenceSequence />
      </section>

      {/* Principles Strip */}
      <section className="mt-principle-strip" aria-label="Core testing principles">
        <span>
          <Route size={18} aria-hidden="true" /> Authorized Target Scope
        </span>
        <span>
          <ScanLine size={18} aria-hidden="true" /> Observable Browser Execution
        </span>
        <span>
          <ShieldCheck size={18} aria-hidden="true" /> Evidence-First Triage
        </span>
      </section>

      {/* 4-Step Visual Workflow */}
      <section className="mt-section" aria-labelledby="workflow-heading">
        <div className="mt-section-heading">
          <p className="mt-kicker">Structured Testing Pipeline</p>
          <h2 id="workflow-heading">
            A clear path from question<br />
            to definitive review.
          </h2>
          <p>
            MarketTwin eliminates guesswork by anchoring every conclusion to observable browser actions
            and verifiable artifacts.
          </p>
        </div>

        <div className="mt-workflow">
          <article className="mt-workflow-step">
            <span className="mt-kicker">01 / Input</span>
            <h3>Define outcome</h3>
            <p>
              Select an authorized application target, specify what users must accomplish, and optionally
              attach approved product specifications to guide the test plan.
            </p>
          </article>
          <article className="mt-workflow-step">
            <span className="mt-kicker">02 / Execution</span>
            <h3>Observe action</h3>
            <p>
              Watch sandboxed browser execution live or replay sequential actions. Pause and take human control
              whenever a sensitive step, CAPTCHA, or MFA checkpoint arises.
            </p>
          </article>
          <article className="mt-workflow-step">
            <span className="mt-kicker">03 / Verification</span>
            <h3>Check evidence</h3>
            <p>
              Inspect time-stamped screenshots, console outputs, and network calls attached directly to each individual step.
              Missing evidence is never masked or substituted.
            </p>
          </article>
          <article className="mt-workflow-step">
            <span className="mt-kicker">04 / Decision</span>
            <h3>Decide next action</h3>
            <p>
              Review results categorized into verified findings, unverified observations, and test runner limitations.
              Export an audit-ready Evidence Ledger.
            </p>
          </article>
        </div>

        <p className="mt-workflow-caveat">
          * Simulated persona journeys surface patterns for review; they do not replace human user research or constitute
          proof without corroborating browser evidence.
        </p>
      </section>

      {/* Sample Report Anatomy / Evidence Categories */}
      <section className="mt-evidence-section" aria-labelledby="anatomy-heading">
        <div className="mt-evidence-intro">
          <p className="mt-kicker">Evidence Classification</p>
          <h2 id="anatomy-heading">
            A claim is a starting point.<br />
            <em>Evidence is the proof.</em>
          </h2>
          <p>
            Agreement between simulated personas can surface an interesting pattern, but only recorded browser
            evidence determines whether that pattern represents an actual product defect.
          </p>
          <Link className="mt-text-link" to="/how-it-works#results">
            Understand the result categories <ArrowRight size={17} aria-hidden="true" />
          </Link>
          <p className="mt-sample-disclaimer">
            Explicitly illustrative: This sample demonstrates MarketTwin's triage classification.
            MarketTwin does not display fabricated customer scores, false pass-rates, or synthetic testimonials.
          </p>
        </div>

        <div className="mt-result-stack">
          <article className="mt-result-card verified">
            <span className="mt-result-marker mt-confirmed" aria-hidden="true" />
            <div>
              <div className="mt-result-card-header">
                <h3>Verified Issues</h3>
                <span className="mt-badge-status-v">Direct Proof</span>
              </div>
              <p>
                Browser evidence directly confirms expected behavior failed or a regression occurred.
                Each finding includes exact step citations, screenshots, and DOM states for immediate reproduction.
              </p>
              <div className="mt-sample-citation">
                <code>Sample: “Annual toggle failed to update checkout total” · Screenshot #art-04, HTTP 422</code>
              </div>
            </div>
          </article>

          <article className="mt-result-card unverified">
            <span className="mt-result-marker mt-unverified" aria-hidden="true" />
            <div>
              <div className="mt-result-card-header">
                <h3>Needs Verification</h3>
                <span className="mt-badge-status-u">Inconclusive</span>
              </div>
              <p>
                An agent reports friction, confusion, or a potential issue, but the supporting evidence is
                partial, missing, or ambiguous. Kept visible for triage without creating false alarms.
              </p>
              <div className="mt-sample-citation">
                <code>Sample: “Persona noted ambiguous tier disclaimer” · Interaction completed, no error logged</code>
              </div>
            </div>
          </article>

          <article className="mt-result-card execution">
            <span className="mt-result-marker mt-execution" aria-hidden="true" />
            <div>
              <div className="mt-result-card-header">
                <h3>Execution Issues</h3>
                <span className="mt-badge-status-e">Runner Limitation</span>
              </div>
              <p>
                Browser timeouts, target network policy stops, or tool errors prevented the step from completing.
                Separated from product bugs so infrastructure boundaries are never confused with software defects.
              </p>
              <div className="mt-sample-citation">
                <code>Sample: “Navigation outside approved origin halted by policy” · Step 04 stopped</code>
              </div>
            </div>
          </article>
        </div>
      </section>

      {/* Who is it for? Strip */}
      <section className="mt-section mt-audience-section" aria-labelledby="audience-heading">
        <div className="mt-section-heading">
          <p className="mt-kicker">Who Is It For?</p>
          <h2 id="audience-heading">Designed for precision across product teams.</h2>
          <p>MarketTwin provides distinct value to every stakeholder in the software delivery lifecycle.</p>
        </div>

        <div className="mt-audience-grid">
          <article>
            <span className="mt-kicker">QA & Test Leads</span>
            <h3>Reproducible Proof</h3>
            <p>
              Replace vague bug reports with deterministic step sequences, time-stamped screenshots, and
              verifiable criteria coverage.
            </p>
          </article>
          <article>
            <span className="mt-kicker">Developers</span>
            <h3>Zero-Guess Diagnostics</h3>
            <p>
              Pinpoint the exact step ID, failed selector, network payload, and console log without having to
              reproduce edge cases manually.
            </p>
          </article>
          <article>
            <span className="mt-kicker">Product Leaders</span>
            <h3>Clear Outcome Clarity</h3>
            <p>
              Know whether critical user journeys succeed or fail against defined criteria, free from inflated
              severity claims or subjective noise.
            </p>
          </article>
          <article>
            <span className="mt-kicker">Security & Ops</span>
            <h3>Strict Policy Guardrails</h3>
            <p>
              Enforce authorized hostnames, prevent unapproved network egress, and inspect immutable audit
              receipts for every test run.
            </p>
          </article>
        </div>
      </section>

      {/* Closing Call to Action */}
      <section className="mt-closing" aria-labelledby="closing-heading">
        <p className="mt-kicker">Make your next review concrete</p>
        <h2 id="closing-heading">
          From “something feels wrong”<br />
          to the step worth inspecting.
        </h2>
        <div className="mt-actions-center">
          <Link className="mt-button" to="/login">
            Open workspace <ArrowRight size={18} aria-hidden="true" />
          </Link>
          <Link className="mt-text-link" to="/how-it-works">
            Read technical overview
          </Link>
        </div>
      </section>
    </PublicLayout>
  );
}

export function HowPage() {
  return (
    <PublicLayout title="How it works">
      {/* Header Section */}
      <section className="mt-how-hero" aria-labelledby="how-hero-heading">
        <p className="mt-kicker">Technical Architecture & Flow</p>
        <h1 id="how-hero-heading">
          A product question.<br />
          An authorized scope.<br />
          <em>An evidence trail.</em>
        </h1>
        <p className="mt-lead">
          MarketTwin bridges high-level testing intent and sandboxed browser execution. Learn how
          targets are scoped, tests are executed, and results are categorized.
        </p>
        <nav className="mt-anchor-nav" aria-label="Section jump links">
          <a href="#setup">01 / Scope & Setup</a>
          <a href="#trace">02 / Trace Pipeline</a>
          <a href="#execution">03 / Execution Modes</a>
          <a href="#results">04 / Result Triage</a>
          <a href="#inconclusive">05 / Inconclusive Factors</a>
          <a href="#limits">06 / Boundaries & Limits</a>
        </nav>
      </section>

      {/* Section 01: Setup & Scope */}
      <section className="mt-how-section" id="setup">
        <div className="mt-how-header">
          <p className="mt-kicker">01 / Scope & Authorization</p>
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
            <h3>Enforce strict network egress policy</h3>
            <p>
              Each target configuration includes an allowed origins list. MarketTwin monitors all outbound browser
              network requests. If a journey attempts to navigate to or fetch resources from an unapproved external domain,
              the request is policy-blocked to prevent unintended data leakage or third-party test pollution.
            </p>
          </article>

          <article>
            <h3>Optional approved product knowledge</h3>
            <p>
              Teams may attach reviewed product specifications, OpenAPI schemas, or user documentation to an application.
              This knowledge grounds the test planner in expected behavior. However, source documentation is treated as
              context, not as proof that live browser code functions properly.
            </p>
          </article>
        </div>
      </section>

      {/* Section 02: Trace Pipeline Flow */}
      <section className="mt-how-section" id="trace">
        <div className="mt-how-header">
          <p className="mt-kicker">02 / The Evidence Trace</p>
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
          <p className="mt-kicker">03 / Dual Execution Modes</p>
          <h2>Persona journeys vs. deterministic feature cases.</h2>
        </div>
        <div className="mt-how-body">
          <div className="mt-modes-grid">
            <article className="mt-mode-card">
              <div className="mt-mode-card-header">
                <Route size={20} aria-hidden="true" />
                <h3>Simulated Persona Mode</h3>
              </div>
              <p>
                The test planner provisions up to 3 distinct simulated personas (such as a first-time user,
                an exploratory tester, or an experienced customer). Missions are allocated based on depth:
              </p>
              <ul className="mt-mode-specs">
                <li><strong>Low Depth:</strong> 1 mission per persona (up to 3 journeys)</li>
                <li><strong>Medium Depth:</strong> 2 missions per persona (up to 6 journeys)</li>
                <li><strong>High Depth:</strong> Up to 4 missions per persona (up to 12 journeys)</li>
              </ul>
              <p className="mt-mode-note">
                <strong>Important caveat:</strong> Synthetic personas explore autonomously. Agreement among simulated
                personas is a prompt for investigation, not independent proof of a defect.
              </p>
            </article>

            <article className="mt-mode-card">
              <div className="mt-mode-card-header">
                <FileCheck2 size={20} aria-hidden="true" />
                <h3>Deep Feature Mode (deep_feature_v1)</h3>
              </div>
              <p>
                Deterministic execution of planned verification checks against explicit functional assertions.
                This mode does not utilize synthetic personas.
              </p>
              <ul className="mt-mode-specs">
                <li>Structured step-by-step actions executed systematically</li>
                <li>Direct assertion evaluation against DOM states and HTTP codes</li>
                <li>Ideal for regression runs, critical happy paths, and CI/CD validation</li>
              </ul>
              <p className="mt-mode-note">
                Produces consistent, reproducible evidence packages specifically tailored for engineering triage.
              </p>
            </article>
          </div>
        </div>
      </section>

      {/* Section 04: Result Triage */}
      <section className="mt-how-section" id="results">
        <div className="mt-how-header">
          <p className="mt-kicker">04 / Result Triage</p>
          <h2>Know what each category proves.</h2>
        </div>
        <div className="mt-how-body">
          <div className="mt-how-result-group">
            <article className="mt-how-result">
              <span className="mt-result-marker mt-confirmed" aria-hidden="true" />
              <div>
                <h3>Verified Issues</h3>
                <p>
                  Direct browser evidence proves the reported issue. Inspect the cited journey, step number,
                  and screenshot before choosing a fix. Confirmed issue totals in the Evidence Ledger include
                  only this verified category.
                </p>
              </div>
            </article>

            <article className="mt-how-result">
              <span className="mt-result-marker mt-unverified" aria-hidden="true" />
              <div>
                <h3>Needs Verification</h3>
                <p>
                  Agent reports, repeated claims, or unexpected stops where supporting screenshots or DOM logs
                  are ambiguous or inconclusive. Repetition across synthetic personas does not elevate severity;
                  all uncorroborated items remain labeled as needing verification.
                </p>
              </div>
            </article>

            <article className="mt-how-result">
              <span className="mt-result-marker mt-execution" aria-hidden="true" />
              <div>
                <h3>Execution Issues</h3>
                <p>
                  A failed browser command, network timeout, or policy block prevented the test from completing
                  its journey. These diagnostics describe a runner limitation and are strictly isolated from product defects.
                </p>
              </div>
            </article>
          </div>

          <div className="mt-how-summary-note">
            <h4>Reading the Evidence Ledger Report</h4>
            <p>
              Start by reviewing the target scope and completed journeys, then investigate high-severity verified findings.
              Open the cited artifact links to view the actual screenshot. An empty findings list does not guarantee a
              defect-free product.
            </p>
          </div>
        </div>
      </section>

      {/* Section 05: Inconclusive Test Reasons */}
      <section className="mt-how-section" id="inconclusive">
        <div className="mt-how-header">
          <p className="mt-kicker">05 / Diagnostic Guide</p>
          <h2>Common reasons a test is inconclusive.</h2>
        </div>
        <div className="mt-how-body">
          <p className="mt-how-body-lead">
            When a journey produces an inconclusive result, it typically stems from one of the following factors
            rather than an inherent product failure:
          </p>

          <div className="mt-disclosures" role="region" aria-label="Inconclusive test reasons">
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
                the journey as inconclusive.
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
                “Evidence unavailable.” Adjacent screenshots are never substituted to maintain cryptographic audit integrity.
              </p>
            </details>

            <details>
              <summary>
                <span>Synthetic persona mission divergence</span>
                <ChevronDown size={18} aria-hidden="true" className="mt-disclosure-arrow" />
              </summary>
              <p>
                In exploratory persona mode, an agent may explore irrelevant links or exhaust its maximum step budget
                before fulfilling the primary mission criteria. These journeys are cataloged as unverified observations.
              </p>
            </details>

            <details>
              <summary>
                <span>Evaluator queue backlog or worker timeout</span>
                <ChevronDown size={18} aria-hidden="true" className="mt-disclosure-arrow" />
              </summary>
              <p>
                Browser execution and automated evaluation are separate processes. If evaluation is queued or the evaluator
                worker experiences latency, the test run remains in an evaluation-pending state until verified.
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
            <h3>Human-in-the-Loop (HITL) Assistance</h3>
            <p>
              When a supported run encounters CAPTCHA, payment authorization, or sensitive identity verification,
              it pauses and requests human intervention. A designated operator can lease the live browser session,
              complete the manual action, and return control seamlessly to the automated runner.
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
              MarketTwin operates with local workspace authentication. Only email addresses authorized by the workspace
              administrator can initiate test runs, inspect sensitive artifacts, or modify network policies.
            </p>
          </article>
        </div>
      </section>

      {/* Closing Action */}
      <section className="mt-closing" aria-labelledby="how-closing-heading">
        <h2 id="how-closing-heading">Ready to inspect a browser journey?</h2>
        <div className="mt-actions-center">
          <Link className="mt-button" to="/login">
            Open workspace <ArrowRight size={18} aria-hidden="true" />
          </Link>
          <Link className="mt-text-link" to="/">
            Back to home
          </Link>
        </div>
      </section>
    </PublicLayout>
  );
}

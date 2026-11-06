import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ConceptFooter, ConceptHeader, StatusPill, TriptychSignature } from "../../components/concept";
import {
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  Route,
  ScanLine,
  ShieldCheck,
} from "lucide-react";

function PublicLayout({ title, children }: { title: string; children: ReactNode }) {
  const navigate = useNavigate();

  useEffect(() => {
    document.title = `${title} · MarketTwin`;
    if (!window.location.hash) window.scrollTo({ top: 0 });
  }, [title]);

  const handleConceptNavigate = (destination: string) => {
    switch (destination) {
      case "Landing page":
        navigate("/");
        break;
      case "How it works":
        navigate("/how-it-works");
        break;
      case "Example report":
      case "Test results":
        navigate("/examples/results");
        break;
      case "Dashboard":
        navigate("/examples/dashboard");
        break;
      case "Watch live":
        navigate("/examples/watch");
        break;
      case "Sign in":
        navigate("/login");
        break;
      case "Add an app":
        navigate("/applications/new");
        break;
      case "Your apps":
      case "Tests":
      case "Testers":
      case "Settings":
        navigate("/login");
        break;
      default:
        break;
    }
  };

  return (
    <div style={{ backgroundColor: "var(--paper)", color: "var(--ink)", minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <a className="mt-skip" href="#public-content">
        Skip to content
      </a>
      <ConceptHeader
        onNavigate={handleConceptNavigate}
        onSignIn={() => navigate("/login")}
        onStartTest={() => navigate("/applications/new")}
      />
      <main id="public-content" tabIndex={-1} style={{ flex: 1 }}>
        {children}
      </main>
      <ConceptFooter onNavigate={handleConceptNavigate} />
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
    action: "Open profile",
    targetUrl: "https://target.example.invalid/profile",
    observation: "Profile opened.",
    evidenceKind: "Recorded browser step",
    evidenceId: "step-11",
    statusText: "Recorded",
    criterion: "Profile page is available",
  },
  {
    stepNumber: "02",
    action: "Choose email updates",
    targetUrl: "https://target.example.invalid/profile",
    observation: "Control selected.",
    evidenceKind: "Recorded browser step",
    evidenceId: "step-12",
    statusText: "Recorded",
    criterion: "Email updates can be selected",
  },
  {
    stepNumber: "03",
    action: "Verify saved state",
    targetUrl: "https://target.example.invalid/profile",
    observation: "Email updates enabled.",
    evidenceKind: "Recorded assertion",
    evidenceId: "step-13",
    statusText: "Passed assertion",
    criterion: "Email updates enabled",
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
          Inspect a recorded step
        </span>
        <span className="mt-badge-demo" aria-label="Illustrative demonstration label">
          Illustrative observation sequence
        </span>
      </div>

      <div className="mt-instrument-context">
        <div className="mt-question-callout">
          <span className="mt-kicker">Testing Question</span>
          <p className="mt-question-text">
            “Can a test user update a profile using the documented form?”
          </p>
        </div>
        <div className="mt-target-tag">
          <span className="mt-kicker">Authorized target:</span>
          <code>https://target.example.invalid</code>
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
          <h3>{step.action}</h3>
          <dl className="mt-demo-comparison">
            <div><dt>Expected</dt><dd>{step.criterion}</dd></div>
            <div><dt>Observed</dt><dd>{step.observation}</dd></div>
          </dl>

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
        Illustrative example. Your workspace shows the steps and artifacts recorded for your test; unavailable evidence stays explicit.
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
            Test real journeys.<br />
            <em>Read the evidence.</em>
          </h1>
          <p className="mt-lead">
            Run browser tests against authorized targets. Inspect recorded actions, assertions, and available artifacts to understand what the evidence supports.
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
            to evidence review.
          </h2>
          <p>
            Move from a testing goal to recorded steps, then review what those steps establish and what remains uncertain.
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
              Follow browser execution and recorded activity. When the agent requests assistance, use the available controls within the approved target scope.
            </p>
          </article>
          <article className="mt-workflow-step">
            <span className="mt-kicker">03 / Verification</span>
            <h3>Check evidence</h3>
            <p>
              Inspect recorded steps, assertions, and the artifacts available for that step. Missing evidence remains visible.
            </p>
          </article>
          <article className="mt-workflow-step">
            <span className="mt-kicker">04 / Decision</span>
            <h3>Decide next action</h3>
            <p>
              Review results categorized into verified findings, unverified observations, and test runner limitations.
              Open the evidence supporting each conclusion.
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
            Illustrative result categories. Your report reflects the evidence recorded for your test.
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
  const cardStyle: CSSProperties = {
    backgroundColor: "var(--card)",
    border: "1px solid var(--line)",
    borderRadius: "10px",
    boxShadow: "var(--shadow-soft)",
    padding: "24px",
  };
  const kickerStyle: CSSProperties = { color: "var(--flame-deep)", margin: "0 0 12px" };
  const sectionTitleStyle: CSSProperties = { margin: "0 0 12px", maxWidth: "640px" };
  const bodyStyle: CSSProperties = { color: "var(--ink-2)", margin: 0 };

  const steps: Array<{ kicker: string; title: string; cards: Array<{ heading: string; text: string }> }> = [
    {
      kicker: "01 / TEACH IT YOUR APP",
      title: "Start with what your app is supposed to do.",
      cards: [
        {
          heading: "Add your app",
          text: "Give MarketTwin your app's address and say which environment it may test. Nothing runs until you authorize that target.",
        },
        {
          heading: "Add what you know",
          text: "Attach your docs, help pages or videos. Testers learn how things should work from them — the docs are context, never proof.",
        },
        {
          heading: "Boundaries are enforced",
          text: "Each target has an allowed-origins list. If a tester tries to wander outside it, the browser is stopped by policy.",
        },
      ],
    },
    {
      kicker: "02 / EXPLORE, THEN APPROVE",
      title: "Testers explore first. You approve the checklist.",
      cards: [
        {
          heading: "Explore — no verdict yet",
          text: "Testers click through your app and map what is actually there: pages, buttons, forms and flows. They do not pass or fail anything in this step.",
        },
        {
          heading: "A checklist in plain words",
          text: "What they found becomes a checklist you can read: “A visitor can buy a t-shirt”, “The discount code lowers the total”. Nothing is judged against a check you have not seen.",
        },
        {
          heading: "Approve it, and it freezes",
          text: "When you approve, that exact checklist is frozen. Every later run tests against the same words, so results can be compared run to run.",
        },
      ],
    },
    {
      kicker: "03 / TESTERS RUN IT",
      title: "Three perspectives try the same tasks, independently.",
      cards: [
        {
          heading: "Different people, different luck",
          text: "An expert, a first-time user, and someone in a hurry on their phone each try the tasks on their own. One tester passing does not hide another one failing.",
        },
        {
          heading: "Watch it happen live",
          text: "Follow each tester's browser as it works — the step it is on, in plain words, with screenshots as it goes. No spinner theatre: you see the real screen.",
        },
        {
          heading: "Stuck means it asks you",
          text: "If a tester reaches something only a person should do — a sign-in challenge, a payment confirmation — the test pauses and asks for your help instead of guessing.",
        },
      ],
    },
  ];

  const couldNotCheck: Array<{ title: string; text: string }> = [
    {
      title: "The page or connection failed",
      text: "A timeout, a slow connection or a page that never finishes loading means that attempt could not be checked. It is recorded as could not check — never quietly counted as worked or broken.",
    },
    {
      title: "A sign-in or challenge blocked the way",
      text: "Login screens, CAPTCHAs and multi-factor prompts pause the tester. Unless you step in to help, that part stays could not check.",
    },
    {
      title: "The target's own boundaries stopped it",
      text: "If a step needs a page outside the target's authorized origins, policy stops the browser. That is a boundary doing its job, not a defect in your app.",
    },
    {
      title: "Evidence could not be captured",
      text: "If a screenshot cannot be taken, the step says so. A neighbouring screenshot is never substituted to make the report look complete.",
    },
  ];

  return (
    <PublicLayout title="How it works">
      {/* Hero */}
      <section aria-labelledby="how-hero-heading" style={{ paddingTop: "72px", paddingBottom: "56px" }}>
        <div className="concept-marketing-container">
          <p className="font-meta-label" style={kickerStyle}>
            HOW IT WORKS
          </p>
          <h1 id="how-hero-heading" className="font-display" style={{ margin: "0 0 24px", maxWidth: "760px" }}>
            Your app, tested like a person — with proof.
          </h1>
          <p className="font-body" style={{ color: "var(--ink-2)", maxWidth: "640px", margin: "0 0 28px" }}>
            MarketTwin sends testers with different perspectives into your app.
            They explore it, you approve what “working” means, and then they
            check it — in real browsers, with screenshots for every claim.
          </p>
          <nav aria-label="On this page" style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {[
              ["#teach", "01 · Teach"],
              ["#verdict", "04 · The verdict"],
              ["#could-not-check", "05 · Could not check"],
              ["#limits", "06 · Honest limits"],
            ].map(([href, label]) => (
              <a
                key={href}
                href={href}
                className="font-grid-cell"
                style={{
                  padding: "8px 16px",
                  borderRadius: "999px",
                  border: "1px solid var(--line)",
                  backgroundColor: "var(--card)",
                  color: "var(--ink)",
                  textDecoration: "none",
                  fontWeight: 500,
                }}
              >
                {label}
              </a>
            ))}
          </nav>
        </div>
      </section>

      {/* Steps 01–03 */}
      <section id="teach" aria-label="How a test runs" style={{ paddingBottom: "8px" }}>
        <div className="concept-marketing-container">
          {steps.map((step) => (
            <div key={step.kicker} style={{ padding: "40px 0" }}>
              <p className="font-meta-label" style={kickerStyle}>{step.kicker}</p>
              <h2 className="font-h2-marketing" style={sectionTitleStyle}>{step.title}</h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "16px" }}>
                {step.cards.map((card) => (
                  <article key={card.heading} style={cardStyle}>
                    <h3 className="font-h3" style={{ margin: "0 0 8px" }}>{card.heading}</h3>
                    <p className="font-body-small" style={bodyStyle}>{card.text}</p>
                  </article>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* The verdict — peach band, the signature visual */}
      <section id="verdict" aria-labelledby="verdict-heading" style={{ backgroundColor: "var(--band-peach)", padding: "64px 0", marginTop: "40px" }}>
        <div className="concept-marketing-container">
          <p className="font-meta-label" style={kickerStyle}>04 / ONE VERDICT</p>
          <h2 id="verdict-heading" className="font-h2-marketing" style={sectionTitleStyle}>
            Every attempt lands in one of three words.
          </h2>
          <p className="font-body" style={{ color: "var(--ink-2)", maxWidth: "640px", margin: "0 0 20px" }}>
            <strong style={{ color: "var(--ink)" }}>Worked</strong>,{" "}
            <strong style={{ color: "var(--ink)" }}>Broken</strong>, or{" "}
            <strong style={{ color: "var(--ink)" }}>Could not check</strong> —
            the same three words on every page of the product. A problem only
            counts as confirmed when it happens again on a re-check, with
            screenshots from both attempts.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "28px" }}>
            <StatusPill status="Worked" />
            <StatusPill status="Broken" />
            <StatusPill status="Could not check" />
            <StatusPill status="Not checked" />
          </div>
          <TriptychSignature />
        </div>
      </section>

      {/* Could not check */}
      <section id="could-not-check" aria-labelledby="could-heading" style={{ padding: "64px 0" }}>
        <div className="concept-marketing-container">
          <p className="font-meta-label" style={kickerStyle}>05 / COULD NOT CHECK</p>
          <h2 id="could-heading" className="font-h2-marketing" style={sectionTitleStyle}>
            “We could not check” is an answer, not a footnote.
          </h2>
          <p className="font-body" style={{ color: "var(--ink-2)", maxWidth: "640px", margin: "0 0 24px" }}>
            Some attempts cannot be completed honestly. MarketTwin says which
            ones, and why — it never folds them into “worked” to make the
            numbers look better.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {couldNotCheck.map((item) => (
              <details key={item.title} style={cardStyle}>
                <summary className="font-h3" style={{ cursor: "pointer", fontSize: "16px" }}>
                  {item.title}
                </summary>
                <p className="font-body-small" style={{ ...bodyStyle, marginTop: "8px" }}>{item.text}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* Honest limits — lilac band */}
      <section id="limits" aria-labelledby="limits-heading" style={{ backgroundColor: "var(--band-lilac)", padding: "64px 0" }}>
        <div className="concept-marketing-container">
          <p className="font-meta-label" style={kickerStyle}>06 / HONEST LIMITS</p>
          <h2 id="limits-heading" className="font-h2-marketing" style={sectionTitleStyle}>
            What MarketTwin does not claim.
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "16px" }}>
            <article style={cardStyle}>
              <h3 className="font-h3" style={{ margin: "0 0 8px" }}>Not real user research</h3>
              <p className="font-body-small" style={bodyStyle}>
                Testers show you how your app behaves, not how real customers
                feel about your product. Use it alongside talking to people,
                not instead of it.
              </p>
            </article>
            <article style={cardStyle}>
              <h3 className="font-h3" style={{ margin: "0 0 8px" }}>Not a certification</h3>
              <p className="font-body-small" style={bodyStyle}>
                A passing run is not an accessibility (WCAG) certificate or a
                security audit. It is evidence about the tasks that were
                checked, on the day they were checked.
              </p>
            </article>
            <article style={cardStyle}>
              <h3 className="font-h3" style={{ margin: "0 0 8px" }}>Only where you allow</h3>
              <p className="font-body-small" style={bodyStyle}>
                MarketTwin tests only targets you authorize, inside the
                network boundaries you set. An empty results list means
                nothing was found in what was checked — not that an app has
                no problems anywhere.
              </p>
            </article>
          </div>
        </div>
      </section>

      {/* Closing CTA — plum band, same as the concept landing */}
      <section aria-labelledby="how-closing-heading" style={{ backgroundColor: "var(--plum)", padding: "72px 0" }}>
        <div className="concept-marketing-container" style={{ textAlign: "center" }}>
          <h2
            id="how-closing-heading"
            className="font-h2-marketing on-dark"
            style={{ color: "#FFFFFF", margin: "0 auto 16px", maxWidth: "560px" }}
          >
            See it on your own app.
          </h2>
          <p className="font-body on-dark" style={{ color: "rgba(255,255,255,0.75)", margin: "0 auto 28px", maxWidth: "480px" }}>
            Add your app's address and watch three testers try it — the first
            verdict comes with its proof attached.
          </p>
          <Link
            to="/applications/new"
            className="font-button-label on-dark"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              minHeight: "44px",
              padding: "12px 24px",
              backgroundColor: "var(--flame-deep)",
              color: "#FFFFFF",
              textDecoration: "none",
            }}
          >
            START A TEST <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </section>
    </PublicLayout>
  );
}

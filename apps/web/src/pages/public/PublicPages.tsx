import "../../styles/marketing.css";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ConceptFooter, ConceptHeader, ConceptStatusPill, TriptychSignature } from "../../components/concept";
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
                  <ArrowRight size={16} aria-hidden="true" />
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
                <CheckCircle2 size={16} aria-hidden="true" /> {step.statusText}
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

export function HowPage() {
  const cardStyle: CSSProperties = {
    backgroundColor: "var(--card)",
    border: "1px solid var(--line)",
    borderRadius: "10px",
    boxShadow: "var(--shadow-soft)",
    padding: "24px",
  };
  const kickerStyle: CSSProperties = { color: "var(--flame-deep)", margin: "0 0 24px" };
  const bandKickerStyle: CSSProperties = { color: "var(--flame-label-band)", margin: "0 0 24px" };
  const sectionTitleStyle: CSSProperties = { margin: "0 0 12px", maxWidth: "640px" };
  const bodyStyle: CSSProperties = { color: "var(--ink-2)", margin: 0 };

  const steps: Array<{ kicker: string; title: string; cards: Array<{ heading: string; text: string }> }> = [
    {
      kicker: "01 / TEACH IT YOUR APP",
      title: "Start with what your app is supposed to do.",
      cards: [
        {
          heading: "Add your app",
          text: "Give MarketTwin your app’s address and say which environment it may test. Nothing runs until you authorize that target.",
        },
        {
          heading: "Add what you know",
          text: "Attach your docs, help pages or videos. Testers learn how things should work from them. The docs are context, never proof.",
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
          heading: "Explore, no verdict yet",
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
          text: "Follow each tester’s browser as it works: the step it is on, in plain words, with screenshots as it goes. No spinner theatre: you see the real screen.",
        },
        {
          heading: "Stuck means it asks you",
          text: "If a tester reaches something only a person should do (a sign-in challenge, a payment confirmation), the test pauses and asks for your help instead of guessing.",
        },
      ],
    },
  ];

  const couldNotCheck: Array<{ title: string; text: string }> = [
    {
      title: "The page or connection failed",
      text: "A timeout, a slow connection or a page that never finishes loading means that attempt could not be checked. It is recorded as could not check, never quietly counted as worked or broken.",
    },
    {
      title: "A sign-in or challenge blocked the way",
      text: "Login screens, CAPTCHAs and multi-factor prompts pause the tester. Unless you step in to help, that part stays could not check.",
    },
    {
      title: "The target’s own boundaries stopped it",
      text: "If a step needs a page outside the target’s authorized origins, policy stops the browser. That is a boundary doing its job, not a defect in your app.",
    },
    {
      title: "Evidence could not be captured",
      text: "If a screenshot cannot be taken, the step says so. A neighbouring screenshot is never substituted to make the report look complete.",
    },
  ];

  return (
    <PublicLayout title="How it works">
      {/* Hero */}
      <section aria-labelledby="how-hero-heading" style={{ paddingTop: "72px", paddingBottom: "80px" }}>
        <div className="concept-marketing-container">
          <p className="font-meta-label" style={kickerStyle}>
            HOW IT WORKS
          </p>
          <h1 id="how-hero-heading" className="font-display" style={{ margin: "0 0 24px", maxWidth: "760px" }}>
            Your app, tested like a person, with proof.
          </h1>
          <p className="font-body" style={{ color: "var(--ink-2)", maxWidth: "640px", margin: "0 0 28px" }}>
            MarketTwin sends testers with different perspectives into your app.
            They explore it, you approve what “working” means, and then they
            check it in real browsers, with screenshots for every claim.
          </p>
          <nav aria-label="On this page" style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {[
              ["#teach", "01 · Teach"],
              ["#explore", "02 · Explore"],
              ["#run", "03 · Testers run"],
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

      {/* Steps 01–03 — each step shows its own object, not the same card grid */}
      <section aria-label="How a test runs" style={{ paddingBottom: "8px" }}>
        <div className="concept-marketing-container">
          {steps.map((step, stepIndex) => (
            <div
              key={step.kicker}
              id={["teach", "explore", "run"][stepIndex]}
              style={{ padding: "40px 0" }}
            >
              <p className="font-meta-label" style={kickerStyle}>{step.kicker}</p>
              <h2 className="font-h2-marketing" style={sectionTitleStyle}>{step.title}</h2>
              {stepIndex === 1 ? (
                <>
                  {/* 02 shows the actual checklist, not three more cards */}
                  <h3 className="font-h3" style={{ margin: "0 0 8px" }}>{step.cards[0].heading}</h3>
                  <p className="font-body" style={{ ...bodyStyle, maxWidth: "640px", margin: "0 0 20px" }}>
                    {step.cards[0].text}
                  </p>
                  <div style={{ ...cardStyle, maxWidth: "760px" }}>
                    <h3 className="font-h3" style={{ margin: "0 0 4px" }}>{step.cards[1].heading}</h3>
                    <p className="font-body-small" style={{ ...bodyStyle, margin: "0 0 12px" }}>
                      {step.cards[1].text}
                    </p>
                    <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                      {["A visitor can buy a t-shirt", "The discount code lowers the total"].map((line) => (
                        <li
                          key={line}
                          className="font-body"
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "12px",
                            padding: "10px 0",
                            borderTop: "1px solid var(--line)",
                            color: "var(--ink)",
                          }}
                        >
                          <span
                            aria-hidden="true"
                            style={{
                              width: "16px",
                              height: "16px",
                              flexShrink: 0,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              fontSize: "11px",
                              lineHeight: 1,
                              color: "var(--flame-deep)",
                              border: "1.5px solid var(--ink-faint)",
                              borderRadius: "3px",
                              backgroundColor: "var(--surface-muted)",
                            }}
                          >✓</span>
                          {line}
                        </li>
                      ))}
                    </ul>
                    <div style={{ borderTop: "1px solid var(--line)", paddingTop: "12px", marginTop: "4px" }}>
                      <h3 className="font-h3" style={{ margin: "0 0 8px" }}>{step.cards[2].heading}</h3>
                      <p className="font-body-small" style={bodyStyle}>{step.cards[2].text}</p>
                    </div>
                  </div>
                </>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "16px" }}>
                  {step.cards.map((card) => (
                    <article key={card.heading} style={cardStyle}>
                      <h3 className="font-h3" style={{ margin: "0 0 8px" }}>{card.heading}</h3>
                      <p className="font-body-small" style={bodyStyle}>{card.text}</p>
                    </article>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* The verdict — peach band, the signature visual */}
      <section id="verdict" aria-labelledby="verdict-heading" style={{ backgroundColor: "var(--band-peach)", padding: "64px 0", marginTop: "40px" }}>
        <div className="concept-marketing-container">
          <p className="font-meta-label" style={bandKickerStyle}>04 / ONE VERDICT</p>
          <h2 id="verdict-heading" className="font-h2-marketing" style={sectionTitleStyle}>
            Every attempt lands in one of three words.
          </h2>
          <p className="font-body" style={{ color: "var(--ink-2)", maxWidth: "640px", margin: "0 0 20px" }}>
            <strong style={{ color: "var(--ink)", fontWeight: 600 }}>Worked</strong>,{" "}
            <strong style={{ color: "var(--ink)", fontWeight: 600 }}>Broken</strong>, or{" "}
            <strong style={{ color: "var(--ink)", fontWeight: 600 }}>Could not check</strong>.
            The same three words on every page of the product. A problem only
            counts as confirmed when it happens again on a re-check, with
            screenshots from both attempts.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "28px" }}>
            <ConceptStatusPill status="Worked" />
            <ConceptStatusPill status="Broken" />
            <ConceptStatusPill status="Could not check" />
            <ConceptStatusPill status="Not checked" />
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
            ones, and why. It never folds them into “worked” to make the
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
          <p className="font-meta-label" style={bandKickerStyle}>06 / HONEST LIMITS</p>
          <h2 id="limits-heading" className="font-h2-marketing" style={sectionTitleStyle}>
            What MarketTwin does not claim.
          </h2>
          {/* 06 is a plain ruled list — no cards, the limits read as limits */}
          <div>
            {[
              {
                heading: "Not real user research",
                text: "Testers show you how your app behaves, not how real customers feel about your product. Use it alongside talking to people, not instead of it.",
              },
              {
                heading: "Not a certification",
                text: "A passing run is not an accessibility (WCAG) certificate or a security audit. It is evidence about the tasks that were checked, on the day they were checked.",
              },
              {
                heading: "Only where you allow",
                text: "MarketTwin tests only targets you authorize, inside the network boundaries you set. An empty results list means nothing was found in what was checked — not that an app has no problems anywhere.",
              },
            ].map((row) => (
              <div
                key={row.heading}
                className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-2 md:gap-8"
                style={{ borderTop: "1px solid var(--ink)", padding: "20px 0" }}
              >
                <h3 className="font-h3" style={{ margin: 0 }}>{row.heading}</h3>
                <p className="font-body" style={{ ...bodyStyle, maxWidth: "640px" }}>{row.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Closing CTA — plum band, same as the concept landing */}
      <section aria-labelledby="how-closing-heading" style={{ backgroundColor: "var(--plum)", padding: "64px 0" }}>
        <div className="concept-marketing-container">
          <h2
            id="how-closing-heading"
            className="font-h2-marketing on-dark"
            style={{ color: "var(--ink-on-dark)", margin: "0 0 16px", maxWidth: "760px" }}
          >
            See it on your own app.
          </h2>
          <p className="font-body on-dark" style={{ color: "rgba(255,255,255,0.75)", margin: "0 0 28px", maxWidth: "640px" }}>
            Add your app’s address and watch three testers try it. The first
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
              color: "var(--ink-on-dark)",
              textDecoration: "none",
            }}
          >
            START A TEST
          </Link>
        </div>
      </section>
    </PublicLayout>
  );
}

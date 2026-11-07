import React, { useRef, useState } from "react";
import {
  CANONICAL_DEMO_DATA,
  ConceptPayload,
} from "../../lib/concept-dataset";
import {
  ConceptFooter,
  ConceptHeader,
  CoverageBar,
  ProofChip,
  TriptychSignature,
  UrlIntakeForm,
  VerdictBlock,
} from "../../components/concept";

interface LandingPageProps {
  data?: ConceptPayload;
  onNavigate?: (destination: string) => void;
  onStartTest?: (url: string) => void;
  className?: string;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  data = CANONICAL_DEMO_DATA,
  onNavigate,
  onStartTest,
  className = "",
}) => {
  const [heroTab, setHeroTab] = useState<"app" | "example" | "how">("app");
  const [exampleCardTab, setExampleCardTab] = useState<"results" | "watch">("results");
  const urlInputRef = useRef<HTMLInputElement | null>(null);

  const handleStartTest = () => {
    // Scroll to intake form and focus input
    const input = document.getElementById("url-input") || document.querySelector("input[placeholder='yourapp.com']");
    if (input) {
      input.scrollIntoView({ behavior: "smooth" });
      (input as HTMLInputElement).focus();
    }
  };

  return (
    <div
      className={`concept-landing-page min-h-screen ${className}`}
      style={{
        backgroundColor: "var(--paper)",
        color: "var(--ink)",
      }}
    >
      {/* 1. Announcement Bar 36px (Plum #221244) */}
      <div
        className="w-full flex items-center justify-center font-meta-label transition-colors"
        style={{
          height: "36px",
          backgroundColor: "var(--plum)",
          color: "var(--ink-on-dark)",
          paddingLeft: "16px",
          paddingRight: "16px",
        }}
      >
        <button
          type="button"
          onClick={() => onNavigate && onNavigate("Example report")}
          className="on-dark hover:underline flex items-center gap-1 cursor-pointer"
          style={{ background: "none", border: "none", color: "var(--ink-on-dark)", padding: 0 }}
        >
          <span>New: see a full example test, start to finish</span>
        </button>
      </div>

      {/* 2. Marketing Header 64px */}
      <ConceptHeader
        onNavigate={onNavigate}
        onSignIn={() => onNavigate && onNavigate("Sign in")}
        onStartTest={handleStartTest}
      />

      {/* 3. Hero Section — copy and form left, the signature right, first screen */}
      <section
        style={{
          paddingTop: "40px",
          paddingBottom: "48px",
          backgroundColor: "var(--paper)",
        }}
      >
        <div className="concept-marketing-container">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 lg:gap-14 items-start">
            <div>
              {/* Eyebrow */}
              <div
                className="font-meta-label"
                style={{ color: "var(--flame-deep)", marginBottom: "16px" }}
              >
                YOUR APP, TESTED LIKE A PERSON
              </div>

              {/* H1 */}
              <h1
                className="font-display"
                style={{
                  color: "var(--ink)",
                  maxWidth: "720px",
                  margin: "0 0 24px 0",
                }}
              >
                Know if your app is ready, before your customers find out.
              </h1>

              {/* Lede — one sentence */}
              <p
                className="font-body"
                style={{
                  color: "var(--ink-2)",
                  maxWidth: "640px",
                  margin: "0 0 28px 0",
                }}
              >
                Three testers (an expert, a first-timer, and someone in a hurry
                on their phone) try your app the way real people do, and you
                get one honest answer, with proof: what worked, what broke, and
                what we could not check.
              </p>

              {/* URL Intake Form */}
              <UrlIntakeForm
                onValidSubmit={(_origin, url) => {
                  onStartTest?.(url);
                }}
              />

              {/* Promise line — under the form, where it backs the action up */}
              <p
                className="font-body-small"
                style={{
                  fontWeight: 600,
                  color: "var(--ink)",
                  margin: "4px 0 0 0",
                }}
              >
                We only call something broken when the evidence proves it, twice.
              </p>
            </div>

            {/* The signature, inside the first screen */}
            <TriptychSignature compact={true} />
          </div>

          {/* Segmented Hero Control (Tablist) */}
          <div style={{ marginTop: "40px" }}>
            <div
              role="tablist"
              aria-label="Getting started options"
              className="flex items-center gap-2 border-b"
              style={{ borderColor: "var(--line)", marginBottom: "16px", flexWrap: "wrap" }}
            >
              {[
                { id: "app", label: "I have an app to test" },
                { id: "example", label: "Show me an example" },
                { id: "how", label: "How it works" },
              ].map((t) => {
                const isSelected = heroTab === t.id;
                return (
                  <button
                    key={t.id}
                    role="tab"
                    aria-selected={isSelected}
                    onClick={() => setHeroTab(t.id as "app" | "example" | "how")}
                    className="font-button-label transition-colors"
                    style={{
                      minHeight: "44px",
                      padding: "12px 16px",
                      background: "none",
                      border: "none",
                      color: isSelected ? "var(--ink)" : "var(--ink-2)",
                      cursor: "pointer",
                      whiteSpace: "nowrap",
                      boxShadow: isSelected ? "inset 0 -2px 0 var(--ink)" : "none",
                    }}
                  >
                    {t.label}
                  </button>
                );
              })}
            </div>

            {/* Panel 1 */}
            {heroTab === "app" && (
              <p className="font-body-small" style={{ color: "var(--ink-2)" }}>
                One address is enough. No setup, no scripts.
              </p>
            )}

            {/* Panel 2 */}
            {heroTab === "example" && (
              <p className="font-body-small" style={{ color: "var(--ink-2)" }}>
                See our Thread &amp; Co. test below with 18 attempts, 3 viewpoints, and 2 confirmed problems.
              </p>
            )}

            {/* Panel 3 */}
            {heroTab === "how" && (
              <p className="font-body-small" style={{ color: "var(--ink-2)" }}>
                1. Tell us the address. 2. Testers try it for real. 3. You get one honest answer.
              </p>
            )}
          </div>
        </div>
      </section>

      {/* 5. Stat Band (Boxless, 1px line top + bottom) */}
      <section
        style={{
          borderTop: "1px solid var(--line)",
          borderBottom: "1px solid var(--line)",
          padding: "72px 0 40px",
          backgroundColor: "var(--paper)",
        }}
      >
        <div className="concept-marketing-container">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
            <div>
              <div className="font-stat-numeral" style={{ color: "var(--ink)", marginBottom: "4px" }}>
                18
              </div>
              <div className="font-body-small" style={{ color: "var(--ink-2)" }}>
                attempts in a full test
              </div>
            </div>

            <div>
              <div className="font-stat-numeral" style={{ color: "var(--ink)", marginBottom: "4px" }}>
                3
              </div>
              <div className="font-body-small" style={{ color: "var(--ink-2)" }}>
                testers, 3 viewpoints
              </div>
            </div>

            <div>
              <div className="font-stat-numeral" style={{ color: "var(--ink)", marginBottom: "4px" }}>
                2
              </div>
              <div className="font-body-small" style={{ color: "var(--ink-2)" }}>
                problems confirmed in the example
              </div>
            </div>

            <div>
              <div className="font-stat-numeral" style={{ color: "var(--ink)", marginBottom: "4px" }}>
                0
              </div>
              <div className="font-body-small" style={{ color: "var(--ink-2)" }}>
                scores you have to decode
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 6. Example Card Section */}
      <section style={{ padding: "88px 0", backgroundColor: "var(--paper)" }}>
        <div className="concept-marketing-container">
          <h2
            className="font-h2-marketing"
            style={{ color: "var(--ink)", margin: "0 0 24px 0" }}
          >
            A real test, written the way yours will be.
          </h2>

          <div
            style={{
              backgroundColor: "var(--card)",
              border: "1px solid var(--line)",
              borderRadius: "10px",
              padding: "24px",
              boxShadow: "var(--shadow-soft)",
            }}
          >
            {/* WAI-ARIA tablist inside example card */}
            <div
              role="tablist"
              aria-label="Example test views"
              className="flex items-center gap-2 border-b"
              style={{ borderColor: "var(--line)", marginBottom: "24px", overflowX: "auto", flexWrap: "nowrap" }}
            >
              <button
                role="tab"
                aria-selected={exampleCardTab === "results"}
                onClick={() => setExampleCardTab("results")}
                className="font-button-label transition-colors"
                style={{
                  minHeight: "44px",
                  padding: "12px 16px",
                  background: "none",
                  border: "none",
                  whiteSpace: "nowrap",
                  color: exampleCardTab === "results" ? "var(--ink)" : "var(--ink-2)",
                  cursor: "pointer",
                  boxShadow: exampleCardTab === "results" ? "inset 0 -2px 0 var(--ink)" : "none",
                }}
              >
                Test results
              </button>
              <button
                role="tab"
                aria-selected={exampleCardTab === "watch"}
                onClick={() => setExampleCardTab("watch")}
                className="font-button-label transition-colors"
                style={{
                  minHeight: "44px",
                  padding: "12px 16px",
                  background: "none",
                  border: "none",
                  whiteSpace: "nowrap",
                  color: exampleCardTab === "watch" ? "var(--ink)" : "var(--ink-2)",
                  cursor: "pointer",
                  boxShadow: exampleCardTab === "watch" ? "inset 0 -2px 0 var(--ink)" : "none",
                }}
              >
                Watch live
              </button>
            </div>

            {exampleCardTab === "results" ? (
              <div>
                <VerdictBlock
                  word={data.verdict.word}
                  reason={data.verdict.reason}
                  honestInputs={data.verdict.honestInputs}
                  isH1={false}
                  compact={true}
                  className="mb-6"
                />

                <div style={{ marginBottom: "24px" }}>
                  <CoverageBar totals={data.totals} />
                </div>

                <div className="flex flex-col gap-4" style={{ marginBottom: "24px" }}>
                  <div className="example-finding-row p-3 border rounded-md" style={{ borderColor: "var(--line)" }}>
                    <div>
                      <div className="font-h3" style={{ fontSize: "16px", color: "var(--ink)" }}>
                        {data.problems[0].title}
                      </div>
                      <div className="font-body-small" style={{ color: "var(--ink-2)" }}>
                        {data.problems[0].description}
                      </div>
                    </div>
                    <ProofChip screenshots={data.problems[0].proof.screenshots} rechecked={true} />
                  </div>

                  <div className="example-finding-row p-3 border rounded-md" style={{ borderColor: "var(--line)" }}>
                    <div>
                      <div className="font-h3" style={{ fontSize: "16px", color: "var(--ink)" }}>
                        {data.problems[1].title}
                      </div>
                      <div className="font-body-small" style={{ color: "var(--ink-2)" }}>
                        {data.problems[1].description}
                      </div>
                    </div>
                    <ProofChip screenshots={null} rechecked={true} />
                  </div>
                </div>

                <div className="flex flex-col gap-3">
                  {data.feelings.map((f, i) => (
                    <div key={i} className="border-t pt-2" style={{ borderColor: "var(--line)" }}>
                      <blockquote className="font-quote" style={{ fontSize: "18px", lineHeight: "26px", margin: "0 0 4px 0", color: "var(--ink)" }}>
                        &ldquo;{f.quote}&rdquo;
                      </blockquote>
                      <div className="font-meta-label" style={{ color: "var(--ink-2)" }}>
                        {f.tester.toUpperCase()} · {f.task.toUpperCase()}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                <div className="font-body-small" style={{ color: "var(--ink-2)" }}>
                  Snapshot: 1 of 3 testers finished · 9 of 18 attempts done
                </div>
                <div className="p-3 border rounded-md" style={{ borderColor: "var(--line)" }}>
                  <div className="font-body font-semibold">Tom (Expert)</div>
                  <div className="font-body-small" style={{ color: "var(--ink-2)" }}>✓ All 6 attempts · Done</div>
                </div>
                <div className="p-3 border rounded-md" style={{ borderColor: "var(--line)" }}>
                  <div className="font-body font-semibold">Maya (First-time user)</div>
                  <div className="font-body-small" style={{ color: "var(--ink-2)" }}>At checkout — about to pay · 2 steps left</div>
                </div>
                <div className="p-3 border rounded-md" style={{ borderColor: "var(--line)" }}>
                  <div className="font-body font-semibold">Priya (Impatient mobile user)</div>
                  <div className="font-body-small" style={{ color: "var(--ink-2)" }}>Track an order — waiting for a login · Waiting 6 minutes</div>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* 7. How It Works Section (Peach Band #FCE8D8) */}
      <section style={{ padding: "88px 0", backgroundColor: "var(--band-peach)" }}>
        <div className="concept-marketing-container">
          <h2
            className="font-h2-marketing"
            style={{ color: "var(--ink)", margin: "0 0 40px 0" }}
          >
            How it works
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div>
              <div
                className="font-stat-numeral"
                style={{ color: "var(--flame-deep)", marginBottom: "8px" }}
              >
                1
              </div>
              <h3 className="font-h3" style={{ color: "var(--ink)", margin: "0 0 8px 0" }}>
                Tell us the address
              </h3>
              <p className="font-body" style={{ color: "var(--ink)", margin: 0 }}>
                One address is enough. No setup, no scripts.
              </p>
            </div>

            <div>
              <div
                className="font-stat-numeral"
                style={{ color: "var(--flame-deep)", marginBottom: "8px" }}
              >
                2
              </div>
              <h3 className="font-h3" style={{ color: "var(--ink)", margin: "0 0 8px 0" }}>
                Testers try it for real
              </h3>
              <p className="font-body" style={{ color: "var(--ink)", margin: 0 }}>
                They click, type and pay like people do, and get stuck like people do.
              </p>
            </div>

            <div>
              <div
                className="font-stat-numeral"
                style={{ color: "var(--flame-deep)", marginBottom: "8px" }}
              >
                3
              </div>
              <h3 className="font-h3" style={{ color: "var(--ink)", margin: "0 0 8px 0" }}>
                You get one answer
              </h3>
              <p className="font-body" style={{ color: "var(--ink)", margin: 0 }}>
                Worked, broken, or could not check, each with the screenshots to prove it.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 8. What You Get Section (Lilac Band #E4E0F5) */}
      <section style={{ padding: "88px 0", backgroundColor: "var(--band-lilac)" }}>
        <div className="concept-marketing-container">
          <h2
            className="font-h2-marketing"
            style={{ color: "var(--ink)", margin: "0 0 40px 0" }}
          >
            What you get
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-8">
            <div style={{ borderTop: "1px solid var(--ink)", paddingTop: "16px" }}>
              <h3 className="font-h3" style={{ color: "var(--ink)", margin: "0 0 6px 0" }}>
                One verdict word
              </h3>
              <p className="font-body" style={{ color: "var(--ink)", margin: 0 }}>
                One word, one reason, and what the test was based on.
              </p>
            </div>

            <div style={{ borderTop: "1px solid var(--ink)", paddingTop: "16px" }}>
              <h3 className="font-h3" style={{ color: "var(--ink)", margin: "0 0 6px 0" }}>
                Every attempt counted
              </h3>
              <p className="font-body" style={{ color: "var(--ink)", margin: 0 }}>
                Every attempt counted, including the ones we could not check.
              </p>
            </div>

            <div style={{ borderTop: "1px solid var(--ink)", paddingTop: "16px" }}>
              <h3 className="font-h3" style={{ color: "var(--ink)", margin: "0 0 6px 0" }}>
                Problems, confirmed twice
              </h3>
              <p className="font-body" style={{ color: "var(--ink)", margin: 0 }}>
                A problem counts only when it fails again on a second check.
              </p>
            </div>

            <div style={{ borderTop: "1px solid var(--ink)", paddingTop: "16px" }}>
              <h3 className="font-h3" style={{ color: "var(--ink)", margin: "0 0 6px 0" }}>
                Feelings, in their words
              </h3>
              <p className="font-body" style={{ color: "var(--ink)", margin: 0 }}>
                How it felt, in the tester&apos;s own words, never a score.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 9. Feelings Section ("How it felt") */}
      <section style={{ padding: "88px 0", backgroundColor: "var(--paper)" }}>
        <div className="concept-marketing-container">
          <h2
            className="font-h2-marketing"
            style={{ color: "var(--ink)", margin: "0 0 40px 0" }}
          >
            How it felt
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {data.feelings.map((f, i) => (
              <div key={i} className="flex flex-col justify-between">
                <blockquote
                  className="font-quote"
                  style={{ color: "var(--ink)", margin: "0 0 16px 0" }}
                >
                  &ldquo;{f.quote}&rdquo;
                </blockquote>
                <div className="font-meta-label" style={{ color: "var(--ink-2)" }}>
                  {f.tester.toUpperCase()} · {f.task.toUpperCase()}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 10. Final CTA Section (Rose Band #F9DEE4) — same two-column posture as the hero */}
      <section style={{ padding: "88px 0", backgroundColor: "var(--band-rose)" }}>
        <div className="concept-marketing-container">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 lg:gap-14 items-center">
            <div>
              <h2
                className="font-h2-marketing"
                style={{ color: "var(--ink)", margin: "0 0 16px 0" }}
              >
                Find out before your customers do.
              </h2>
              <p className="font-body" style={{ color: "var(--ink)", margin: 0 }}>
                A full test takes about 20 minutes.
              </p>
            </div>

            <UrlIntakeForm
              onValidSubmit={(_origin, url) => {
                onStartTest?.(url);
              }}
            />
          </div>
        </div>
      </section>

      {/* 11. Footer */}
      <ConceptFooter onNavigate={onNavigate} />
    </div>
  );
};

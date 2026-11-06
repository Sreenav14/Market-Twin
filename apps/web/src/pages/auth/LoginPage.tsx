import { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Spinner } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { ConceptFooter, ConceptHeader, TriptychSignature } from "../../components/concept";
import { ApiError, CurrentUser, api } from "../../lib/api";

export function LoginPage({
  onAuthenticated,
}: {
  onAuthenticated: (user: CurrentUser) => void;
}) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    document.title = "Sign in · MarketTwin";
    inputRef.current?.focus();
  }, []);

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
      case "Add an app":
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      const user = await api.login(email.trim());
      onAuthenticated(user);
    } catch (loginError) {
      const message =
        loginError instanceof ApiError && loginError.status >= 500
          ? "The login service is unavailable. Please try again when your workspace service is running."
          : loginError instanceof Error
          ? loginError.message
          : "Unable to sign in. Please try again.";
      setError(message);
      setTimeout(() => {
        errorRef.current?.focus();
      }, 50);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <div style={{ backgroundColor: "var(--paper)", color: "var(--ink)", minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <ConceptHeader
        onNavigate={handleConceptNavigate}
        onSignIn={() => inputRef.current?.focus()}
        onStartTest={() => inputRef.current?.focus()}
      />

      <main style={{ flex: 1, width: "100%" }}>
        <div
          className="concept-marketing-container signin-layout"
          style={{ paddingTop: "56px", paddingBottom: "72px" }}
        >
          {/* Sign-in form — the same card, field and button as everywhere else */}
          <section aria-labelledby="signin-form-title" style={{ minWidth: 0 }}>
            <p className="font-meta-label" style={{ color: "var(--flame-deep)", margin: "0 0 12px" }}>
              SIGN IN
            </p>
            <h1 id="signin-form-title" className="font-h2-marketing" style={{ margin: "0 0 12px" }}>
              Welcome back.
            </h1>
            <p className="font-body" style={{ color: "var(--ink-2)", margin: "0 0 28px", maxWidth: "420px" }}>
              See what your testers found — what worked, what broke, and what
              could not be checked.
            </p>

            <div
              style={{
                backgroundColor: "var(--card)",
                border: "1px solid var(--line)",
                borderRadius: "10px",
                boxShadow: "var(--shadow-soft)",
                padding: "24px",
              }}
            >
              <form onSubmit={submit} aria-busy={busy}>
                <label htmlFor="email" className="field-label">
                  Work email
                </label>
                <Input
                  id="email"
                  ref={inputRef}
                  type="email"
                  inputMode="email"
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    if (error) setError(null);
                  }}
                  placeholder="name@company.com"
                  autoComplete="email"
                  autoCapitalize="none"
                  spellCheck={false}
                  required
                  autoFocus
                  aria-describedby={error ? "signin-help signin-error" : "signin-help"}
                  style={{ width: "100%" }}
                />
                <p id="signin-help" className="form-help" style={{ margin: "8px 0 0" }}>
                  Use the email address authorized for your workspace.
                </p>

                <div aria-live="assertive" style={{ minHeight: "8px" }}>
                  {error ? (
                    <p
                      id="signin-error"
                      ref={errorRef}
                      tabIndex={-1}
                      className="form-error"
                      role="alert"
                      style={{ margin: "12px 0 0" }}
                    >
                      {error}
                    </p>
                  ) : null}
                </div>

                <Button
                  type="submit"
                  disabled={busy || !email.trim()}
                  style={{ width: "100%", marginTop: "16px", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "8px" }}
                >
                  {busy ? (
                    <>
                      <Spinner />
                      <span>Signing in…</span>
                    </>
                  ) : (
                    <>
                      <span>Continue to workspace</span>
                      <ArrowRight size={18} aria-hidden="true" />
                    </>
                  )}
                </Button>
              </form>
            </div>

            <p className="font-body-small" style={{ color: "var(--ink-2)", margin: "16px 0 0" }}>
              Need access? Ask your workspace administrator to add your email
              address to the authorized users list.
            </p>
          </section>

          {/* The product's own visual: three looks, one verdict */}
          <section aria-label="What MarketTwin shows you" style={{ minWidth: 0 }}>
            <p className="font-meta-label" style={{ color: "var(--ink-faint)", margin: "0 0 12px" }}>
              THREE LOOKS, ONE VERDICT
            </p>
            <TriptychSignature compact />
            <p className="font-body-small" style={{ color: "var(--ink-2)", margin: "16px 0 0", maxWidth: "560px" }}>
              Three testers try your app independently — an expert, a first-time
              user, and someone in a hurry on their phone. Their results are put
              together into one verdict, with the screenshots to prove it.
            </p>
          </section>
        </div>
      </main>

      <ConceptFooter onNavigate={handleConceptNavigate} />
    </div>
  );
}

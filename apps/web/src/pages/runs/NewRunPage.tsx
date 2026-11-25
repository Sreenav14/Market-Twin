import { FormEvent, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Link,
  useNavigate,
  useOutletContext,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { ArrowRight, Check, ShieldCheck } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import {
  EmptyState,
  ErrorPanel,
  LoadingPanel,
  Spinner,
} from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { ErrorSummary, FieldError, RequiredMark } from "../../components/ui/Field";
import { InlineAlert } from "../../components/ui/Feedback";
import { ApiError, api, type TestingDepth } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { AppShellContext } from "../../layouts/AppShell";

const examples = [
  {
    title: "Pricing clarity",
    brief:
      "Can a first-time customer understand our pricing and confidently choose the right plan?",
  },
  {
    title: "First-time setup",
    brief:
      "Can a new user complete account setup and understand what to do next without help?",
  },
  {
    title: "Checkout confidence",
    brief:
      "Can a shopper review the full cost and complete checkout without uncertainty?",
  },
];
function isLoopbackHost(host: string) {
  const normalized = host.replace(/^\[|\]$/g, "");
  if (normalized === "localhost" || normalized === "::1") return true;
  const octets = normalized.split(".").map(Number);
  return octets.length === 4 && octets[0] === 127 && octets.every((part) => Number.isInteger(part) && part >= 0 && part <= 255);
}
export function NewRunPage({ applicationIdOverride, fixedKind }: { applicationIdOverride?: string; fixedKind?: "slop" } = {}) {
  const { applicationId: routeApplicationId = "" } = useParams();
  const applicationId = applicationIdOverride ?? routeApplicationId;
  const [params] = useSearchParams();
  const requestedTarget = params.get("target") ?? "";
  const navigate = useNavigate();
  const { workspace, user } = useOutletContext<AppShellContext>();
  const [targetId, setTargetId] = useState("");
  const [brief, setBrief] = useState("");
  const [name, setName] = useState("");
  const [testingDepth, setTestingDepth] = useState<TestingDepth>("medium");
  const [allowOffsiteNavigation, setAllowOffsiteNavigation] = useState(false);
  const requestedMode = params.get("mode");
  // U-P8: one create flow, three run kinds. Legacy ?mode= values map
  // onto their unified successor kinds.
  const initialKind = requestedMode === "legacy_persona" || requestedMode === "persona"
    ? "persona"
    : requestedMode === "slop" ? "slop" : "explore_test";
  const [runKind, setRunKind] = useState(fixedKind ?? initialKind);
  const [humanActionApprovals, setHumanActionApprovals] = useState(false);
  const [sensitiveActionRules, setSensitiveActionRules] = useState("[]");
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [syntheticFixtureApproval, setSyntheticFixtureApproval] = useState(false);
  const [harnessRunMode, setHarnessRunMode] = useState<"read_only" | "standard">("read_only");
  const [approvedTestData, setApprovedTestData] = useState<{ key: string; value: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Punish late, reward early (Spec 3 §6.2/§6.4): a failed submit
  // produces an error summary plus per-field messages; each message
  // clears the instant its value is fixed (derived, not stored).
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const submitting = useRef(false);
  const creationRequestId = useRef<string | null>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const canWrite = canWriteWorkspace(workspace.role);
  const state = useQuery({
    queryKey: ["test-targets", user.id, applicationId],
    enabled: canWrite,
    queryFn: async () => {
      const [application, targets] = await Promise.all([
        api.getApplication(applicationId),
        api.listTargets(applicationId),
      ]);
      const authorized = await Promise.all(
        targets.map(async (target) => {
          try {
            const authorization = await api.getAuthorization(target.id);
            const valid =
              authorization.status === "authorized" &&
              (!authorization.expires_at ||
                Date.parse(authorization.expires_at) > Date.now());
            return { target, authorized: valid && target.status === "active" };
          } catch (error) {
            if (error instanceof ApiError && error.status === 404)
              return { target, authorized: false };
            throw error;
          }
        }),
      );
      return { application, targets: authorized };
    },
  });
  useEffect(() => {
    if (!brief || busy) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [brief, busy]);
  const targets =
    state.data?.targets
      .filter((item) => item.authorized)
      .map((item) => item.target) || [];
  const selectedTarget = targetId || requestedTarget;
  const target = selectedTarget ? targets.find((item) => item.id === selectedTarget) : targets[0];
  const approvalsEligible = Boolean(
    target && ["local", "development", "test", "staging"].includes(target.environment),
  );
  const fixtureApprovalEligible = Boolean(target && ["local", "test"].includes(target.environment) && target.allowed_origins.length > 0 && (() => {
    try { if (!isLoopbackHost(new URL(target.base_url).hostname)) return false; } catch { return false; }
    return target.allowed_origins.every((origin) => origin.scheme === "http" && !origin.include_subdomains && isLoopbackHost(origin.hostname));
  })());
  useEffect(() => {
    if (!fixtureApprovalEligible || runKind !== "explore_test") {
      setSyntheticFixtureApproval(false);
    }
  }, [fixtureApprovalEligible, runKind]);
  useEffect(() => {
    if (!approvalsEligible || runKind !== "explore_test") {
      setHumanActionApprovals(false);
    }
  }, [approvalsEligible, runKind]);
  const briefError = runKind !== "slop" && submitAttempted && brief.trim().length < 10
    ? "Describe your goal in at least 10 characters."
    : null;
  const targetError = submitAttempted && !target
    ? "Choose an authorized target to continue."
    : null;
  const summaryErrors = [
    ...(targetError ? [{ targetId: "test-target", message: targetError }] : []),
    ...(briefError ? [{ targetId: "test-brief", message: briefError }] : []),
  ];
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    setSubmitAttempted(true);
    if (!target || (runKind !== "slop" && brief.trim().length < 10)) {
      return;
    }
    let parsedRules: unknown[] = [];
    if (humanActionApprovals) {
      try {
        const parsed: unknown = JSON.parse(sensitiveActionRules);
        if (!Array.isArray(parsed)) throw new Error("not a list");
        parsedRules = parsed as unknown[];
      } catch {
        setRulesError("The approval rules must be a JSON list. Fix the rules under Security and authorization, then try again.");
        return;
      }
    }
    setRulesError(null);
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      creationRequestId.current ??= crypto.randomUUID();
      const run = await api.createRun(
        applicationId,
        target.id,
        runKind === "slop" ? "Audit UI quality across all discovered authorized pages and states." : brief.trim(),
        testingDepth,
        name,
        runKind,
        undefined,
        humanActionApprovals && approvalsEligible && runKind === "explore_test",
        syntheticFixtureApproval && fixtureApprovalEligible && runKind === "explore_test",
        humanActionApprovals ? parsedRules : [],
        undefined,
        true,
        allowOffsiteNavigation,
        runKind === "explore_test" ? harnessRunMode : undefined,
        runKind === "explore_test" && harnessRunMode === "standard"
          ? approvedTestData.filter((entry) => entry.key.trim().length > 0)
          : [],
        creationRequestId.current,
      );
      creationRequestId.current = null;
      setBrief("");
      navigate(`/runs/${run.id}/overview`);
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not create the test. Please try again.",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  const header = fixedKind ? null : (
    <PageHeader
      eyebrow="New test"
      title={runKind === "slop" ? "Configure UI audit" : "Start a test"}
      description={runKind === "slop" ? "Audit discoverable authorized pages and UI states; coverage gaps are reported." : "Choose a target, pick the kind of test, and describe what matters."}
    />
  );
  if (!canWrite)
    return (
      <>
        {header}
        <EmptyState
          title="Read-only workspace"
          copy="Your role can review tests. Ask a workspace administrator for permission to create one."
        />
      </>
    );
  if (state.isPending)
    return (
      <>
        {header}
        <LoadingPanel label="Preparing test" />
      </>
    );
  if (state.isError)
    return (
      <>
        {header}
        <ErrorPanel
          message={state.error.message}
          action={
            <Button variant="secondary" onClick={() => void state.refetch()}>
              Try again
            </Button>
          }
        />
      </>
    );
  if (state.data.application.status !== "active")
    return (
      <>
        {header}
        <EmptyState
          title="Application is inactive"
          copy="Choose an active application to start a new test."
          action={
            <Link className="secondary-button" to="/applications">
              Choose application
            </Link>
          }
        />
      </>
    );
  if (state.data.targets.length === 0)
    return (
      <>
        {header}
        <EmptyState
          title="Add a target first"
          copy="Connect an environment for this application before creating a test."
          action={
            <Link
              className="primary-button"
              to={`/applications/${applicationId}/targets/new`}
            >
              Add target
            </Link>
          }
        />
      </>
    );
  if (targets.length === 0)
    return (
      <>
        {header}
        <section className="panel">
          <h2>Authorize a target to continue</h2>
          <p className="muted">
            A test needs an active target with current authorization.
          </p>
          <div className="data-list">
            {state.data.targets.map(({ target }) => (
              <div className="data-row" key={target.id}>
                <ShieldCheck size={20} aria-hidden="true" />
                <div className="row-primary">
                  <strong>{target.name}</strong>
                  <span>{target.environment}</span>
                </div>
                <Link
                  className="text-link"
                  to={`/targets/${target.id}/authorization`}
                >
                  Review authorization
                </Link>
              </div>
            ))}
          </div>
        </section>
      </>
    );
  return (
    <>
      {header}
      <div className="study-create-layout">
        <form className="study-composer" onSubmit={submit} noValidate>
          {submitAttempted && summaryErrors.length ? <ErrorSummary errors={summaryErrors} /> : null}
          {!fixedKind ? <fieldset className="run-create-zone" disabled={busy}>
            <legend>Kind of test</legend>
            {[
              ["explore_test", "Explore & Test"],
              ["persona", "Persona Test"],
              ["slop", "Check the look"],
            ].map(([value, label]) => (
              <label key={value}>
                <input type="radio" name="execution-mode" value={value}
                  checked={runKind === value} onChange={() => setRunKind(value)} />
                {label}
              </label>
            ))}
          </fieldset> : null}
          <section className="run-create-zone" aria-labelledby="what-to-test-heading">
            <h2 id="what-to-test-heading">What to test</h2>
          <div className="composer-knowledge form-grid">
            <label htmlFor="test-name">Test name <RequiredMark required={false} /></label>
            <input className="text-input" id="test-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={80} disabled={busy} placeholder="For example, Pricing clarity" aria-describedby="test-name-help" />
            <p className="form-help" id="test-name-help">A short label for lists and activity. A unique incremental ID is assigned automatically. Your testing goal stays separate below.</p>
          </div>
          <div className="composer-knowledge form-grid">
            <label htmlFor="test-target">{runKind === "explore_test" ? "App" : "Application target"} <RequiredMark required /></label>
            <select
              id="test-target"
              name="target"
              value={target?.id || ""}
              onChange={(event) => setTargetId(event.target.value)}
              aria-invalid={!target || targetError ? true : undefined}
              aria-describedby={!target || targetError ? "test-target-error" : undefined}
            >
              {!target ? <option value="" disabled>Choose an authorized target</option> : null}
              {targets.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.name} · {item.environment}
                </option>
              ))}
            </select>
            {!target ? <FieldError id="test-target-error">The requested target is unavailable or not authorized. Choose an authorized target to continue.</FieldError> : targetError ? <FieldError id="test-target-error">{targetError}</FieldError> : null}
            <p className="form-help">
              <ShieldCheck size={16} aria-hidden="true" />{" "}
              {target ? "Authorized" : "Target required"}
            </p>
          </div>
          {runKind === "explore_test" ? <div className="composer-knowledge form-grid">
            <div className="composer-app-url">
              <label htmlFor="app-url">App URL</label>
              <input id="app-url" className="text-input" readOnly value={target?.base_url || ""} aria-describedby="app-url-help" />
              <p id="app-url-help" className="form-help">Choose an authorized app above to explore its address.</p>
            </div>
          </div> : null}
          {runKind !== "slop" ? <div className="composer-body">
            <label className="composer-label" htmlFor="test-brief">
              {runKind === "explore_test" ? "What is this app and who is it for?" : "Your testing goal"} <RequiredMark required />
            </label>
            <textarea
              ref={textarea}
              id="test-brief"
              name="test-brief"
              value={brief}
              onChange={(event) => {
                setBrief(event.target.value);
                setError(null);
              }}
              placeholder="Can a first-time customer understand our pricing and choose the right plan?…"
              maxLength={4000}
              rows={6}
              aria-describedby={briefError ? "brief-help brief-count brief-error" : "brief-help brief-count"}
              aria-invalid={briefError ? true : undefined}
            />
            <div className="composer-meta">
              <span id="brief-help">
                Describe an outcome, rather than a script of clicks.
              </span>
              <span id="brief-count">
                {brief.length.toLocaleString()} / 4,000
              </span>
            </div>
            <div className="brief-examples">
              <span>Example briefs</span>
              {examples.map((example) => (
                <button
                  key={example.title}
                  className="brief-example-button"
                  type="button"
                  onClick={() => {
                    setBrief(example.brief);
                    textarea.current?.focus();
                  }}
                >
                  {example.title}
                </button>
              ))}
            </div>
          </div> : null}
          </section>
          <section className="run-create-zone" aria-labelledby="how-to-execute-heading">
            <h2 id="how-to-execute-heading">How to execute</h2>
          <div className="composer-knowledge form-grid">
            {runKind === "explore_test" ? <p className="form-help">The agent explores your app, checks every button, field and link it finds, and proves every problem twice before reporting it. This is the only kind that produces a ready / not-ready verdict.</p> : null}
            {runKind === "persona" ? <p className="form-help">Testers with real conditions — slow phone, keyboard only, first visit — walk the app and report what they felt, in their own words. No scores, and it never changes a verdict.</p> : null}
            {runKind === "slop" ? <p className="form-help">Audit UI quality: placeholder content, broken images, contrast, generic wording and JavaScript errors. The score describes measured issues, not whether AI created the site. Review page coverage alongside the score.</p> : null}
            {runKind !== "slop" ? <><label htmlFor="testing-depth">Testing depth</label>
            <select id="testing-depth" value={testingDepth} disabled={busy} onChange={(event) => setTestingDepth(event.target.value as TestingDepth)} aria-describedby="testing-depth-help">
              <option value="low">Low — focused coverage</option>
              <option value="medium">Medium — balanced coverage</option>
              <option value="high">High — broader coverage</option>
            </select>
            <p id="testing-depth-help" className="form-help">{runKind === "explore_test" ? <>Depth controls exploration coverage.</> : <>Depth controls how many personas are selected.</>}</p></> : null}
            {runKind === "explore_test" ? <>
              <fieldset disabled={busy}>
                <legend>Run mode</legend>
                <label>
                  <input type="radio" name="run-mode" value="read_only"
                    checked={harnessRunMode === "read_only"} onChange={() => setHarnessRunMode("read_only")} />
                  Read-only
                </label>
                <p className="form-help">Looks and checks only. Nothing on the site is changed.</p>
                <label>
                  <input type="radio" name="run-mode" value="standard"
                    checked={harnessRunMode === "standard"} onChange={() => setHarnessRunMode("standard")} />
                  Standard
                </label>
                <p className="form-help">Also fills forms and makes reversible changes, using only test data you approve below.</p>
              </fieldset>
              {harnessRunMode === "standard" ? <div className="approved-test-data">
                <p className="form-help">Test data for form fills in this run. The built-in keys valid_name, valid_email, invalid_email and empty are already covered — add a row only to override one of them or to cover a field the built-ins do not fit. Values are stored with the run and never shown in results.</p>
                {approvedTestData.map((entry, index) => (
                  <div className="approved-test-data-row" key={index}>
                    <label>
                      Key
                      <input className="text-input" aria-label={`Test data key ${index + 1}`} value={entry.key} disabled={busy} placeholder="company_name" onChange={(event) => setApprovedTestData((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, key: event.target.value } : row))} />
                    </label>
                    <label>
                      Value
                      <input className="text-input" aria-label={`Test data value ${index + 1}`} value={entry.value} disabled={busy} onChange={(event) => setApprovedTestData((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, value: event.target.value } : row))} />
                    </label>
                    <button type="button" className="text-link" aria-label={`Remove test data row ${index + 1}`} disabled={busy} onClick={() => setApprovedTestData((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}>Remove</button>
                  </div>
                ))}
                <button type="button" className="text-link" disabled={busy} onClick={() => setApprovedTestData((rows) => [...rows, { key: "", value: "" }])}>Add test data</button>
              </div> : null}
            </> : null}
          </div>
          </section>
          <details className="composer-disclosure security-disclosure">
            <summary>Security and authorization</summary>
          <section className="run-create-zone" aria-labelledby="run-security-heading">
            <h2 id="run-security-heading" className="visually-hidden">Security and authorization</h2>
          <p className="form-help">Only controls permitted by the selected target and test mode are available here. Credentials never belong in the test brief or policy fields.</p>
          <label><input type="checkbox" checked={allowOffsiteNavigation} onChange={(event) => setAllowOffsiteNavigation(event.target.checked)} /> Allow off-site navigation</label>
          <p className="form-help">The lead agent checks outside navigation. Outside sites are browse-only, with up to 3 domains and 20 minutes of off-site browsing.</p>
          <p className="form-help">Testers start without login setup. If a login or protected interaction blocks execution, the tester pauses and asks for help. You can take control within approved origins or skip that case or journey.</p>
          {approvalsEligible && runKind === "explore_test" ? (
            <section className="composer-knowledge" aria-labelledby="action-approval-heading">
              <h2 id="action-approval-heading">Sensitive action approval</h2>
              <label className="knowledge-choice">
                <input type="checkbox" className="mt-checkbox" checked={humanActionApprovals} disabled={busy} onChange={(event) => setHumanActionApprovals(event.target.checked)} />
                <span>Pause for owner/admin approval before eligible Save, Create, Update, Publish, or form Submit actions</span>
              </label>
              <p className="form-help">Each approval is bound to one exact action and authorized target, expires after ten minutes, and can be used once. Delete, payment, messaging, role, permission, and data-export actions stay blocked.</p>
              {humanActionApprovals ? <>
                <label htmlFor="sensitive-action-rules">Declared synthetic effects and reset confirmation (JSON)</label>
                <textarea className="text-input" id="sensitive-action-rules" value={sensitiveActionRules} onChange={(event) => { setSensitiveActionRules(event.target.value); setRulesError(null); }} disabled={busy} rows={5} aria-invalid={rulesError ? true : undefined} aria-describedby={rulesError ? "sensitive-action-rules-error" : undefined} />
                {rulesError ? <FieldError id="sensitive-action-rules-error">{rulesError}</FieldError> : null}
                <p className="form-help">Declare the exact button name, category, optional named scope, nonsecret resource reference, and test_data_reset_confirmed: true. Empty rules block all effects. Use dedicated synthetic test data only.</p>
              </> : null}
            </section>
          ) : null}
          {fixtureApprovalEligible && runKind === "explore_test" ? (
            <section className="composer-knowledge" aria-labelledby="fixture-approval-heading">
              <h2 id="fixture-approval-heading">Synthetic fixture assertions</h2>
              <label className="knowledge-choice">
                <input type="checkbox" className="mt-checkbox" checked={syntheticFixtureApproval} disabled={busy} onChange={(event) => setSyntheticFixtureApproval(event.target.checked)} />
                <span>Enable the local registration fixture and its one-time Save approval</span>
              </label>
              <p className="form-help">This enables fixture-grounded assertions and the synthetic Save approval on an all-loopback local/test target.</p>
            </section>
          ) : null}
          </section>
          </details>
          {briefError ? <FieldError id="brief-error">{briefError}</FieldError> : null}
          {error ? (
            <InlineAlert severity="error" title="Could not create the test" role="alert">
              {error}
            </InlineAlert>
          ) : null}
          <div className="composer-footer">
            <p>{"Creates a draft. Start it when you're ready."}</p>
            <Button type="submit" disabled={busy || !target}>
              {busy ? (
                <>
                  <Spinner />
                  Creating…
                </>
              ) : (
                <>
                  {runKind === "slop" ? "Create UI audit" : "Create test"} <ArrowRight size={16} aria-hidden="true" />
                </>
              )}
            </Button>
          </div>
        </form>
        {runKind !== "slop" ? <aside className="study-guidance">
          <h2>Writing the test brief</h2>
          <p>
            Describe who is using the application and what they need to complete.
          </p>
          <ul>
            <li>
              <Check size={16} aria-hidden="true" />
              Name the audience or situation.
            </li>
            <li>
              <Check size={16} aria-hidden="true" />
              Describe what success looks like.
            </li>
            <li>
              <Check size={16} aria-hidden="true" />
              Include any constraints or context.
            </li>
          </ul>
          <div className="guidance-scope">
            <strong>{state.data.application.name}</strong>
            <span>{target?.name}</span>
            <span>
              {target?.requires_auth
                ? "Authentication may be needed"
                : "Public target"}
            </span>
          </div>
        </aside> : null}
      </div>
    </>
  );
}

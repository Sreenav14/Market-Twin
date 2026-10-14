import { FormEvent, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Link,
  useNavigate,
  useOutletContext,
  useParams,
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
export function NewRunPage() {
  const { applicationId = "" } = useParams();
  const navigate = useNavigate();
  const { workspace, user } = useOutletContext<AppShellContext>();
  const [targetId, setTargetId] = useState("");
  const [brief, setBrief] = useState("");
  const [name, setName] = useState("");
  const [testingDepth, setTestingDepth] = useState<TestingDepth>("medium");
  const [executionMode, setExecutionMode] = useState("legacy_persona");
  const [knowledgeIds, setKnowledgeIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const canWrite = canWriteWorkspace(workspace.role);
  const knowledgeState = useQuery({
    queryKey: ["ingestion", user.id, workspace.id, applicationId],
    enabled: canWrite,
    queryFn: () => api.listIngestion(workspace.id, applicationId),
  });
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
  const target = targets.find((item) => item.id === targetId) || targets[0];
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    if (!target || brief.trim().length < 10) {
      setError(
        "Choose an authorized target and describe your goal in at least 10 characters.",
      );
      textarea.current?.focus();
      return;
    }
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      const run = await api.createRun(applicationId, target.id, brief.trim(), knowledgeIds, testingDepth, name, executionMode);
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
  const header = (
    <PageHeader
      eyebrow="New test"
      title="Create a test"
      description="Choose a target and describe the task to test."
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
        <form className="study-composer" onSubmit={submit}>
          <div className="composer-knowledge form-grid">
            <label htmlFor="test-name">Test name <span className="muted">Optional</span></label>
            <input className="text-input" id="test-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={80} disabled={busy} placeholder="For example, Pricing clarity" aria-describedby="test-name-help" />
            <p className="form-help" id="test-name-help">A short label for lists and activity. A unique incremental ID is assigned automatically. Your testing goal stays separate below.</p>
          </div>
          <div className="composer-target">
            <label htmlFor="test-target">Application target</label>
            <select
              id="test-target"
              name="target"
              value={target?.id || ""}
              onChange={(event) => setTargetId(event.target.value)}
            >
              {targets.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.name} · {item.environment}
                </option>
              ))}
            </select>
            <span className="authorized-label">
              <ShieldCheck size={15} aria-hidden="true" />
              Authorized
            </span>
          </div>
          <section className="composer-knowledge" aria-labelledby="test-knowledge-heading">
            <h2 id="test-knowledge-heading">Knowledge for this test <span className="muted">Optional</span></h2>
            <p className="form-help">Select approved knowledge attached to this application before agents are created. You can select up to 10 sets.</p>
            {knowledgeState.isPending ? <p className="form-note" role="status">Loading approved knowledge…</p> : knowledgeState.isError ? (
              <p className="form-error" role="alert">Could not load knowledge. <Button variant="ghost" size="sm" onClick={() => void knowledgeState.refetch()}>Try again</Button></p>
            ) : knowledgeState.data.filter((entry) => entry.status === "approved").length ? (
              <fieldset className="knowledge-choices"><legend className="visually-hidden">Select approved knowledge sets</legend>
                {knowledgeState.data.filter((entry) => entry.status === "approved").map((entry) => (
                  <div className="knowledge-choice" key={entry.id}>
                    <label><input type="checkbox" checked={knowledgeIds.includes(entry.id)} disabled={busy || (knowledgeIds.length >= 10 && !knowledgeIds.includes(entry.id))} onChange={(event) => setKnowledgeIds((previous) => event.target.checked ? [...previous, entry.id] : previous.filter((id) => id !== entry.id))} /><span><strong>{entry.name}</strong><span className="muted">{entry.knowledge_count} knowledge items · {entry.artifact_count} artifacts · {entry.skill_count} Skills</span></span></label>
                    <Link className="text-link" to={`/knowledge/review/${entry.id}`} target="_blank" rel="noreferrer">View<span className="visually-hidden"> {entry.name} in a new tab</span></Link>
                  </div>
                ))}
              </fieldset>
            ) : <p className="muted">No approved knowledge attached yet. <Link className="text-link" to="/knowledge/review" target="_blank" rel="noreferrer">Review knowledge</Link> and attach a set to this application, or continue without knowledge.</p>}
          </section>
          <div className="composer-knowledge form-grid">
            <label htmlFor="testing-depth">Testing depth</label>
            <label htmlFor="execution-mode">Testing mode</label>
            <select id="execution-mode" value={executionMode} disabled={busy} onChange={(event) => setExecutionMode(event.target.value)}>
              <option value="legacy_persona">Persona journeys</option>
              <option value="deep_feature_v1">Feature cases — experimental</option>
            </select>
            {executionMode === "deep_feature_v1" ? <p className="form-help">Tests one bounded feature with recorded assertions. Undocumented expectations remain unverified.</p> : null}
            <select id="testing-depth" value={testingDepth} disabled={busy || executionMode === "deep_feature_v1"} onChange={(event) => setTestingDepth(event.target.value as TestingDepth)} aria-describedby="testing-depth-help">
              <option value="low">Low — focused coverage</option>
              <option value="medium">Medium — balanced coverage</option>
              <option value="high">High — broader coverage</option>
            </select>
            <p id="testing-depth-help" className="form-help">{executionMode === "deep_feature_v1" ? "Feature cases use a separate bounded budget of up to eight cases." : <>Three personas test up to {testingDepth === "low" ? "1 mission (3 journeys)" : testingDepth === "medium" ? "2 missions (6 journeys)" : "4 missions (12 journeys)"}. Broader coverage takes longer.</>}</p>
          </div>
          <div className="composer-body">
            <label className="composer-label" htmlFor="test-brief">
              Your testing goal
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
              aria-describedby={error ? "brief-help brief-count brief-error" : "brief-help brief-count"}
              aria-invalid={Boolean(error)}
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
          </div>
          {error ? (
            <p id="brief-error" className="composer-error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="composer-footer">
            <p>Creates a draft. Start it when you're ready.</p>
            <Button type="submit" disabled={busy}>
              {busy ? (
                <>
                  <Spinner />
                  Creating…
                </>
              ) : (
                <>
                  Create test <ArrowRight size={16} aria-hidden="true" />
                </>
              )}
            </Button>
          </div>
        </form>
        <aside className="study-guidance">
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
        </aside>
      </div>
    </>
  );
}

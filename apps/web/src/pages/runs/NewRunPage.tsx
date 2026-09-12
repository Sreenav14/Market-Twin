import { FormEvent, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { ArrowRight, Check, Lightbulb, ShieldCheck } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel, Spinner } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { ApiError, api } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { AppShellContext } from "../../layouts/AppShell";

const examples = [
  { title: "Pricing clarity", brief: "Can a first-time customer understand our pricing and confidently choose the right plan?" },
  { title: "First-time setup", brief: "Can a new user complete account setup and understand what to do next without help?" },
  { title: "Checkout confidence", brief: "Can a shopper review the full cost and complete checkout without uncertainty?" },
];
export function NewRunPage() {
  const { applicationId = "" } = useParams();
  const navigate = useNavigate();
  const { workspace, user } = useOutletContext<AppShellContext>();
  const [targetId, setTargetId] = useState("");
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const canWrite = canWriteWorkspace(workspace.role);
  const state = useQuery({
    queryKey: ["test-targets", user.id, applicationId], enabled: canWrite,
    queryFn: async () => {
      const [application, targets] = await Promise.all([api.getApplication(applicationId), api.listTargets(applicationId)]);
      const authorized = await Promise.all(targets.map(async target => {
        try {
          const authorization = await api.getAuthorization(target.id);
          const valid = authorization.status === "authorized" && (!authorization.expires_at || Date.parse(authorization.expires_at) > Date.now());
          return { target, authorized: valid && target.status === "active" };
        } catch (error) { if (error instanceof ApiError && error.status === 404) return { target, authorized: false }; throw error; }
      }));
      return { application, targets: authorized };
    },
  });
  useEffect(() => {
    if (!brief || busy) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [brief, busy]);
  const targets = state.data?.targets.filter(item => item.authorized).map(item => item.target) || [];
  const target = targets.find(item => item.id === targetId) || targets[0];
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    if (!target || brief.trim().length < 10) { setError("Choose an authorized target and describe your goal in at least 10 characters."); textarea.current?.focus(); return; }
    submitting.current = true; setBusy(true); setError(null);
    try { const run = await api.createRun(applicationId, target.id, brief.trim()); setBrief(""); navigate(`/runs/${run.id}/overview`); }
    catch (error) { setError(error instanceof Error ? error.message : "Could not create the test. Please try again."); }
    finally { submitting.current = false; setBusy(false); }
  }
  const header = <PageHeader eyebrow="New test" title="What should we test?" description="Choose your app environment and the user experience you want to validate." />;
  if (!canWrite) return <>{header}<EmptyState title="Read-only workspace" copy="Your role can review tests. Ask a workspace administrator for permission to create one." /></>;
  if (state.isPending) return <>{header}<LoadingPanel label="Preparing test" /></>;
  if (state.isError) return <>{header}<ErrorPanel message={state.error.message} action={<Button variant="secondary" onClick={() => void state.refetch()}>Try again</Button>} /></>;
  if (state.data.application.status !== "active") return <>{header}<EmptyState title="Application is inactive" copy="Choose an active application to start a new test." action={<Link className="secondary-button" to="/applications">Choose application</Link>} /></>;
  if (state.data.targets.length === 0) return <>{header}<EmptyState title="Add a target first" copy="Connect an environment for this application before creating a test." action={<Link className="primary-button" to={`/applications/${applicationId}/targets/new`}>Add target</Link>} /></>;
  if (targets.length === 0) return <>{header}<section className="panel"><h2>Authorize a target to continue</h2><p className="muted">A test needs an active target with current authorization.</p><div className="data-list">{state.data.targets.map(({ target }) => <div className="data-row" key={target.id}><ShieldCheck size={20} aria-hidden="true" /><div className="row-primary"><strong>{target.name}</strong><span>{target.environment}</span></div><Link className="text-link" to={`/targets/${target.id}/authorization`}>Review authorization</Link></div>)}</div></section></>;
  return <>{header}<div className="study-create-layout"><form className="study-composer" onSubmit={submit}>
    <div className="composer-target"><label htmlFor="test-target">Application target</label><select id="test-target" name="target" value={target?.id || ""} onChange={event => setTargetId(event.target.value)}>{targets.map(item => <option value={item.id} key={item.id}>{item.name} · {item.environment}</option>)}</select><span className="authorized-label"><ShieldCheck size={15} aria-hidden="true" />Authorized</span></div>
    <div className="composer-body"><label className="composer-label" htmlFor="test-brief">Your testing goal</label><textarea ref={textarea} id="test-brief" name="test-brief" value={brief} onChange={event => { setBrief(event.target.value); setError(null); }} placeholder="Can a first-time customer understand our pricing and choose the right plan?…" maxLength={4000} rows={6} aria-describedby="brief-help brief-count" aria-invalid={Boolean(error)} />
      <div className="composer-meta"><span id="brief-help">Describe an outcome, rather than a script of clicks.</span><span id="brief-count">{brief.length.toLocaleString()} / 4,000</span></div>
      <div className="brief-examples"><span>Try a starting point</span>{examples.map(example => <button key={example.title} type="button" onClick={() => { setBrief(example.brief); textarea.current?.focus(); }}>{example.title}</button>)}</div>
    </div>
    {error ? <p className="composer-error" role="alert">{error}</p> : null}
    <div className="composer-footer"><p>Perspectives and missions are generated for this test.</p><Button type="submit" disabled={busy}>{busy ? <><Spinner />Creating…</> : <>Create test <ArrowRight size={16} aria-hidden="true" /></>}</Button></div>
  </form><aside className="study-guidance"><span className="guidance-icon"><Lightbulb size={22} aria-hidden="true" /></span><h2>A useful test starts with a clear question.</h2><p>Focus on one decision or outcome that matters to your customers.</p><ul><li><Check size={16} aria-hidden="true" />Name the audience or situation.</li><li><Check size={16} aria-hidden="true" />Describe what success looks like.</li><li><Check size={16} aria-hidden="true" />Leave room for different approaches.</li></ul><div className="guidance-scope"><strong>{state.data.application.name}</strong><span>{target?.name}</span><span>{target?.requires_auth ? "Authentication may be needed" : "Public target"}</span></div></aside></div></>;
}

import { DeleteAction } from "../../components/markettwin/DeleteAction";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { Search, ArrowUpRight } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { Button } from "../../components/ui/button";
import { studyBrief, textValue } from "../../lib/format";
import { useWorkspaceStudies } from "../../lib/useWorkspaceStudies";
import { canManageLifecycle, canWriteWorkspace } from "../../lib/permissions";
import { AppShellContext } from "../../layouts/AppShell";

export function RunsPage() {
  const { workspace, user } = useOutletContext<AppShellContext>();
  const state = useWorkspaceStudies(user.id, workspace.id);
  const [params, setParams] = useSearchParams();
  const search = params.get("q") || "";
  const status = params.get("status") || "all";
  const runs = (state.data?.runs || []).filter(run => (status === "all" || run.status === status) && studyBrief(run.configuration_snapshot).toLowerCase().includes(search.toLowerCase()));
  function filter(key: string, value: string) { setParams(previous => { const next = new URLSearchParams(previous); if (!value || value === "all") next.delete(key); else next.set(key, value); return next; }, { replace: true }); }
  return <><PageHeader title="Tests" description="Track your app tests, review usability issues, and see what needs to improve." action={canWriteWorkspace(workspace.role) ? <Link className="primary-button" to="/applications">New test</Link> : undefined} />
    {state.isPending ? <LoadingPanel label="Loading tests" /> : state.isError ? <ErrorPanel message={state.error.message} action={<Button variant="secondary" onClick={() => void state.refetch()}>Try again</Button>} /> : <>
    <div className="filter-bar"><div className="search-field"><Search size={17} aria-hidden="true" /><input aria-label="Search tests" value={search} onChange={event => filter("q", event.target.value)} placeholder="Find a test…" /></div><select className="text-input filter-control" aria-label="Test status" value={status} onChange={event => filter("status", event.target.value)}><option value="all">All statuses</option>{[...new Set(state.data.runs.map(run => run.status))].sort().map(value => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></div>
    {runs.length ? <div className="study-table"><div className="study-table-heading"><span>Test / target</span><span>Status</span></div>{runs.map(run => <div className="deletable-row" key={run.id}><Link className="study-row" to={`/runs/${run.id}/overview`}><span className="study-row-copy"><strong>{studyBrief(run.configuration_snapshot)}</strong><span>{textValue(run.target_snapshot.name, "Target")}<span className="monospace">{run.id.slice(0, 8)}</span></span></span><StatusBadge status={run.status} /><ArrowUpRight size={18} aria-hidden="true" /></Link>{canManageLifecycle(workspace.role) ? <DeleteAction kind="test" id={run.id} name={studyBrief(run.configuration_snapshot)} disabled={!["draft", "completed", "failed", "cancelled"].includes(run.status)} onDeleted={() => { void state.refetch(); }} /> : null}</div>)}</div> : <EmptyState title={state.data.runs.length ? "No matching tests" : "Your first test starts with a question"} copy={state.data.runs.length ? "Try another search or clear your filters." : "Choose an application and describe the experience you want to investigate."} action={state.data.runs.length ? <Button variant="secondary" onClick={() => setParams({})}>Clear filters</Button> : <Link className="primary-button" to="/applications">Choose application</Link>} />}
    </>}
  </>;
}

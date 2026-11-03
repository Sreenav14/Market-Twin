import { FormEvent, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { RunContext } from "../../layouts/RunLayout";
import { ApiError, api, type ContractCheck, type ContractJourney } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { Button } from "../../components/ui/button";
import { ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { RunPreflightPanel } from "../../components/markettwin/RunPreflightPanel";

function stepDescription(step: ContractJourney["steps"][number]) {
  const name = step.target?.name || step.target?.label || step.target?.text;
  const verbs: Record<string, string> = { navigate: "Open", click: "Choose", fill: "Enter safe test data in", select: "Select a safe test option in", check: "Check", uncheck: "Uncheck", go_back: "Go back" };
  return `${verbs[step.action] || step.action} ${name || step.url || ""}`.trim();
}

export function ContractApprovalPage() {
  const { run, workspace, user, refresh } = useOutletContext<RunContext>();
  const navigate = useNavigate();
  const client = useQueryClient();
  const queryKey = ["test-contract", user.id, workspace.id, run.id];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ journey: ContractJourney; check: ContractCheck } | null>(null);
  const [wordingReviewed, setWordingReviewed] = useState(true);
  const state = useQuery({ queryKey, queryFn: () => api.getTestContract(workspace.id, run.id), retry: false,
    refetchInterval: (query) => !query.state.data && !["failed", "cancelled", "completed"].includes(run.status) ? 4000 : false });
  const canWrite = canWriteWorkspace(workspace.role);
  const contract = state.data;
  const preflight = useQuery({ queryKey: ["run-preflight", user.id, run.id],
    queryFn: () => api.getRunPreflight(run.id), enabled: Boolean(contract && ["draft", "approved"].includes(contract.status)), retry: false });
  const editable = canWrite && contract?.status === "draft" && !busy;
  const discovery = run.configuration_snapshot.discovery_map as { features?: unknown[]; journeys?: { journey_key: string; completed: boolean; blocked_reason?: string }[] } | undefined;
  const incomplete = new Set(discovery?.journeys?.filter(j => !j.completed).map(j => j.journey_key));
  const completed = discovery?.journeys?.filter(j => j.completed).length ?? contract?.journeys.filter(j => !j.excluded).length ?? 0;
  const depth = run.configuration_snapshot.testing_depth;
  const journeyLimit = depth === "low" ? 3 : depth === "high" ? 8 : 6;
  const completedContractJourneys = contract?.journeys.filter(journey =>
    discovery?.journeys?.some(item => item.journey_key === journey.journey_key && item.completed),
  ) ?? [];
  const depthExcluded = new Set(completedContractJourneys.slice(journeyLimit).map(journey => journey.journey_key));
  const includedJourneyCount = contract?.journeys.filter(journey =>
    !journey.excluded && journey.assertions.some(assertion => !assertion.excluded),
  ).length ?? 0;
  const loginBlocked = discovery?.journeys?.filter(j => j.blocked_reason === "authentication_required").length ?? 0;
  const origins = run.target_snapshot.allowed_origins as { scheme: string; hostname: string; port?: number | null }[] | undefined;
  const appUrl = typeof run.target_snapshot.base_url === "string" ? run.target_snapshot.base_url : null;
  async function update(journey: ContractJourney, values: { excluded?: boolean; assertions?: ContractCheck[] }) {
    setBusy(true); setError(null);
    try { client.setQueryData(queryKey, await api.updateContractJourney(workspace.id, run.id, journey.journey_key, values)); setEditing(null); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "The tests could not be saved."); }
    finally { setBusy(false); }
  }
  async function approve() {
    if (busy || !contract) return;
    setBusy(true); setError(null);
    try {
      if (contract.status === "draft") client.setQueryData(queryKey, await api.approveTestContract(workspace.id, run.id));
      await api.startTestContract(workspace.id, run.id);
      refresh(); navigate(`/runs/${run.id}/watch`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The tests could not start."); }
    finally { setBusy(false); }
  }
  function saveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    void update(editing.journey, { assertions: editing.journey.assertions.map(check => check.assertion_id === editing.check.assertion_id ? editing.check : check) });
  }
  const waiting = state.isError && state.error instanceof ApiError && state.error.status === 404;
  if (state.isPending || waiting) return <section className="panel"><h2>Approve the tests</h2>{["failed", "cancelled"].includes(run.status) ? <p>Exploration stopped before tests were available.</p> : <LoadingPanel label="Testers are exploring your app. Tests will appear here when exploration is complete." />}</section>;
  if (state.isError) return <ErrorPanel message={state.error.message} />;
  if (!contract) return null;
  return <div className="contract-review">
    <section className="panel"><h2>Approve the tests</h2>
      <p>Testers explored your app and found {discovery?.features?.length ?? "an unknown number of"} features. They completed {completed} journeys. {loginBlocked > 0 ? `${loginBlocked} journeys need a login and were skipped.` : ""}</p>
      <p>These tests run against: {origins?.length ? origins.map(o => `${o.scheme}://${o.hostname}${o.port ? `:${o.port}` : ""}`).join(", ") : appUrl || "App address unavailable"}.</p>
      <p>Review what each journey checks before running it. Approving tests does not grant access to additional apps or approve sensitive actions.</p>
      <p>This run&apos;s {String(depth || "medium")} testing depth allows up to {journeyLimit} journeys. Extra completed journeys start excluded. To test more, create a new run with a higher testing depth.</p>
      {includedJourneyCount > journeyLimit ? <p role="alert">You have included {includedJourneyCount} journeys, above this run's limit of {journeyLimit}. Exclude at least {includedJourneyCount - journeyLimit} before approval.</p> : null}
      {!canWrite ? <p>Your workspace role can review these tests but cannot change or approve them.</p> : null}
      {error ? <p role="alert" className="form-error">{error}</p> : null}
      {completed === 0 ? <><p>No journeys were completed. There are no completed journeys to test.</p><Link to={`/applications/${run.application_id}/runs/new?target=${run.target_id}&mode=discovery_contract_v1`}>Explore again</Link></> : null}
    </section>
    {contract.journeys.map(journey => <section className="panel" key={journey.journey_key} aria-label={journey.title}>
      <h3>{journey.title}</h3><ol>{journey.steps.map((step, i) => <li key={i}>{stepDescription(step)}</li>)}</ol>
      {incomplete.has(journey.journey_key) ? <p>Exploration did not complete this journey. It is excluded from testing.</p> : null}
      {depthExcluded.has(journey.journey_key) ? <p>This completed journey is beyond the selected testing-depth limit and starts excluded.</p> : null}
      <label><input type="checkbox" checked={journey.excluded} disabled={!editable || incomplete.has(journey.journey_key)} onChange={e => void update(journey, { excluded: e.target.checked })} /> Don&apos;t test this</label>
      <ul className="contract-checks">{journey.assertions.map(check => <li key={check.assertion_id}>
        <label><input type="checkbox" checked={!check.excluded} disabled={!editable || journey.excluded} onChange={e => void update(journey, { assertions: journey.assertions.map(a => a.assertion_id === check.assertion_id ? { ...a, excluded: !e.target.checked } : a) })} /> {check.plain_language}</label>{" "}
        <Button variant="ghost" disabled={!editable || journey.excluded} onClick={() => { setWordingReviewed(true); setEditing({ journey, check: { ...check } }); }}>Edit</Button>
      </li>)}</ul>
    </section>)}
    {editing ? <section className="panel" aria-label="Edit check"><form onSubmit={saveEdit}>
      <h3>Edit check</h3>
      <label htmlFor="check-wording">What should happen?</label><textarea id="check-wording" value={editing.check.plain_language} maxLength={500} onChange={e => { setWordingReviewed(true); setEditing({ ...editing, check: { ...editing.check, plain_language: e.target.value } }); }} required />
      <label htmlFor="check-type">Type of check</label><select id="check-type" value={editing.check.oracle} onChange={e => {
        const oracle = e.target.value as ContractCheck["oracle"];
        const control = ["visible", "enabled", "count", "checked"].includes(oracle);
        setWordingReviewed(false);
        setEditing({ ...editing, check: { ...editing.check, oracle, target_role: control ? "button" : null, target_name: control ? "" : null, expected_value: ["visible", "enabled", "checked"].includes(oracle) ? true : oracle === "count" ? 0 : "" } });
      }}>
        {Object.entries({ visible_text: "Text appears", visible: "Control is visible", enabled: "Control is enabled", url_path_v1: "Page address", title: "Page title", count: "Number of matching controls", checked: "Checkbox is checked" }).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      {["visible", "enabled", "count", "checked"].includes(editing.check.oracle) ? <>
        <label htmlFor="check-role">Control type</label><input id="check-role" required maxLength={80} value={editing.check.target_role || ""} onChange={e => setEditing({ ...editing, check: { ...editing.check, target_role: e.target.value } })} />
        <label htmlFor="check-name">Control name</label><input id="check-name" required maxLength={160} value={editing.check.target_name || ""} onChange={e => setEditing({ ...editing, check: { ...editing.check, target_name: e.target.value } })} />
      </> : null}
      <label htmlFor="check-expected">Expected result</label>{["visible", "enabled", "checked"].includes(editing.check.oracle) ? <select id="check-expected" value={String(editing.check.expected_value)} onChange={e => setEditing({ ...editing, check: { ...editing.check, expected_value: e.target.value === "true" } })}><option value="true">Yes</option><option value="false">No</option></select> : <input id="check-expected" type={editing.check.oracle === "count" ? "number" : "text"} min={editing.check.oracle === "count" ? 0 : undefined} maxLength={500} required value={String(editing.check.expected_value ?? "")} onChange={e => {
        const value = ["visible", "enabled", "checked"].includes(editing.check.oracle) ? e.target.value === "true" : editing.check.oracle === "count" ? Number(e.target.value) : e.target.value;
        setWordingReviewed(false);
        setEditing({ ...editing, check: { ...editing.check, expected_value: value } });
      }} />}
      <p className="form-help">Review and update the wording so it matches the selected check and expected result.</p>
      {!wordingReviewed ? <p role="status">Update the wording above before saving this changed check.</p> : null}
      <Button type="submit" disabled={busy || !wordingReviewed}>Save check</Button><Button type="button" variant="ghost" disabled={busy} onClick={() => setEditing(null)}>Cancel</Button>
    </form></section> : null}
    {completed > 0 && contract.status !== "frozen" ? <><RunPreflightPanel data={preflight.data} error={preflight.error?.message} loading={preflight.isFetching} onRefresh={() => void preflight.refetch()} /><footer className="panel contract-approval-footer"><Button disabled={busy || Boolean(editing) || !canWrite || !preflight.data?.ready || !["draft", "approved"].includes(contract.status)} onClick={() => void approve()}>{busy ? "Starting tests…" : "Approve and run tests"}</Button><p>You can exclude every check. In that case, nothing will be verified.</p></footer></> : null}
    {contract.status === "frozen" ? <p>The approved tests are saved. <Link to={`/runs/${run.id}/watch`}>Watch live</Link></p> : null}
  </div>;
}

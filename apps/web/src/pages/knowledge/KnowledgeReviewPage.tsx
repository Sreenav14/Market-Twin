import { useState } from "react";
import { Link, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "../../components/ui/PageHeader";
import { DeleteAction } from "../../components/markettwin/DeleteAction";
import { Button } from "../../components/ui/button";
import { ErrorPanel, LoadingPanel, Spinner } from "../../components/ui/StateViews";
import { api, type IngestionEntry } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { type AppShellContext } from "../../layouts/AppShell";
import { KnowledgeResult } from "./KnowledgeResult";
import { sourceRoles } from "./IngestionPage";
import { IngestionProgress, isIngestionPending } from "./IngestionProgress";
import { KnowledgeApplications, RenameKnowledge } from "./KnowledgeSettings";

export function KnowledgeReviewPage() {
  const navigate = useNavigate();
  const { entryId = "" } = useParams();
  const { workspace, user } = useOutletContext<AppShellContext>();
  const queryClient = useQueryClient();
  const [confirmedFor, setConfirmedFor] = useState<string | null>(null);
  const reviewKey = `${workspace.id}:${entryId}`;
  const confirmed = confirmedFor === reviewKey;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const state = useQuery({ queryKey: ["knowledge-review", user.id, workspace.id, entryId], queryFn: () => api.getIngestion(workspace.id, entryId), refetchInterval: (query) => query.state.data && isIngestionPending(query.state.data) ? 1500 : false });
  const source = useQuery({ queryKey: ["knowledge-source", user.id, workspace.id, entryId], queryFn: () => api.getKnowledgeSourceAccess(workspace.id, entryId), staleTime: 120_000, refetchInterval: 120_000 });
  function saved(entry: IngestionEntry) {
    queryClient.setQueryData(["knowledge-review", user.id, workspace.id, entryId], entry);
    void queryClient.invalidateQueries({ queryKey: ["ingestion", user.id, workspace.id] });
  }
  async function approve() {
    setBusy(true);
    setError(null);
    try {
      const approved = await api.approveIngestion(workspace.id, entryId);
      queryClient.setQueryData(["knowledge-review", user.id, workspace.id, entryId], approved);
      await queryClient.invalidateQueries({ queryKey: ["ingestion", user.id, workspace.id] });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not approve knowledge.");
    } finally { setBusy(false); }
  }
  async function retry() {
    setBusy(true);
    setError(null);
    try {
      const queued = await api.retryIngestion(workspace.id, entryId);
      queryClient.setQueryData(["knowledge-review", user.id, workspace.id, entryId], queued);
      await queryClient.invalidateQueries({ queryKey: ["ingestion", user.id, workspace.id] });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not retry ingestion.");
    } finally { setBusy(false); }
  }
  if (state.isPending) return <LoadingPanel label="Loading knowledge for review" />;
  if (state.isError) return <ErrorPanel message={state.error.message} action={<Button variant="secondary" onClick={() => void state.refetch()}>Try again</Button>} />;
  const entry = state.data;
  const hasKnowledge = Boolean(entry.knowledge_count + entry.artifact_count + entry.skill_count);
  const pending = isIngestionPending(entry);
  const failed = entry.processing_status === "failed";
  return (
    <>
      <Link className="back-link" to="/knowledge/review">Back to review knowledge</Link>
      <PageHeader eyebrow={pending ? "In progress" : failed ? "Processing failed" : entry.status === "approved" ? "Approved knowledge" : "Needs review"} title={entry.name} description={entry.source_name} action={<div className="knowledge-row-actions">
        {source.data ? <a className="secondary-button" href={source.data.url} target="_blank" rel="noreferrer">Open original source</a> : null}
        {canWriteWorkspace(workspace.role) ? <RenameKnowledge entry={entry} onSaved={saved} /> : null}
        {canWriteWorkspace(workspace.role) ? <DeleteAction kind="knowledge" workspaceId={workspace.id} id={entry.id} name={entry.name} disabled={busy} onDeleted={() => navigate("/knowledge/review")} /> : null}
      </div>} />
      {source.isError ? <p className="form-error" role="alert">Could not open the original source. <Button variant="ghost" size="sm" onClick={() => void source.refetch()}>Try again</Button></p> : null}
      <p className="muted">Source purpose: {entry.roles.map((role) => sourceRoles.find(([value]) => value === role)?.[1] ?? role).join(", ")}</p>
      {pending ? <section className="panel section-block">
        <IngestionProgress entry={entry} />
        <p className="muted">You can leave this page. Processing will continue, and the knowledge will appear here when ready.</p>
      </section> : failed ? <section className="panel section-block">
        <p className="form-error" role="alert">{entry.processing_error || "Knowledge processing failed."}</p>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        {canWriteWorkspace(workspace.role) ? <Button variant="secondary" disabled={busy} onClick={() => void retry()}>{busy ? "Retrying…" : "Retry processing"}</Button> : null}
      </section> : <KnowledgeResult preview={entry.preview} />}
      {pending || failed ? null : entry.status === "approved" ? (
        <><section className="panel section-block"><h2>Available for tests</h2><p>This knowledge set is approved. Attach it to an application to make it available when creating tests.</p></section><KnowledgeApplications key={`${entry.id}:${entry.application_ids?.join()}`} entry={entry} onSaved={saved} /></>
      ) : canWriteWorkspace(workspace.role) ? (
        <section className="panel form-grid section-block">
          <h2>Approve for use in tests</h2>
          <p className="muted">Check the facts, procedures, Skills, and source purpose. Leave this set unapproved if any item is incorrect.</p>
          <label className="knowledge-confirmation"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmedFor(event.target.checked ? reviewKey : null)} disabled={busy || !hasKnowledge} />I reviewed this knowledge against its source and confirmed the source purpose.</label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          {!hasKnowledge ? <p className="form-note">This source produced no knowledge to approve.</p> : null}
          <div className="form-actions"><Button disabled={!confirmed || busy || !hasKnowledge} onClick={() => void approve()}>{busy ? <><Spinner /> Approving…</> : "Approve knowledge"}</Button></div>
        </section>
      ) : <p className="muted">Your workspace role can review this set. Write access is required to approve it.</p>}
    </>
  );
}

import { useState } from "react";
import { Link, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, ExternalLink, FileCheck, ShieldCheck } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import { DeleteAction } from "../../components/markettwin/DeleteAction";
import { Button } from "../../components/ui/button";
import { ErrorPanel, LoadingPanel, Spinner } from "../../components/ui/StateViews";
import { api, type IngestionEntry } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { type AppShellContext } from "../../layouts/AppShell";
import { KnowledgeResult } from "./KnowledgeResult";
import { sourceRoles } from "./IngestionPage";
import { ingestionStageLabel, IngestionProgress, isIngestionPending } from "./IngestionProgress";
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

  const state = useQuery({
    queryKey: ["knowledge-review", user.id, workspace.id, entryId],
    queryFn: () => api.getIngestion(workspace.id, entryId),
    refetchInterval: (query) => query.state.data && isIngestionPending(query.state.data) ? 1500 : false,
  });

  const source = useQuery({
    queryKey: ["knowledge-source", user.id, workspace.id, entryId, state.data?.source_name],
    queryFn: () => api.getKnowledgeSourceAccess(workspace.id, entryId),
    enabled: Boolean(state.data),
    staleTime: 120_000,
    refetchInterval: 120_000,
  });

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
    } finally {
      setBusy(false);
    }
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
    } finally {
      setBusy(false);
    }
  }

  if (state.isPending) return <LoadingPanel label="Loading knowledge for review" />;
  if (!state.data) {
    return (
      <ErrorPanel
        message={state.error?.message || "Could not load knowledge."}
        action={<Button variant="secondary" onClick={() => void state.refetch()}>Try again</Button>}
      />
    );
  }

  const entry = state.data;
  const hasKnowledge = Boolean(entry.knowledge_count + entry.artifact_count + entry.skill_count);
  const pending = isIngestionPending(entry);
  const failed = entry.processing_status === "failed";
  const isApproved = entry.status === "approved";
  const isLink = Boolean(entry.original_source_url) ||
    entry.source_name.endsWith("-link.txt") ||
    entry.source_name.startsWith("http://") ||
    entry.source_name.startsWith("https://");

  const eyebrow = pending
    ? "In progress"
    : failed
    ? "Processing failed"
    : isApproved
    ? "Approved knowledge"
    : "Needs review";

  return (
    <div className="knowledge-review-page">
      <Link className="back-link" to="/knowledge/review">Back to review knowledge</Link>
      <PageHeader
        eyebrow={eyebrow}
        title={entry.name}
        description={entry.source_name}
        action={
          <div className="knowledge-row-actions">
            {entry.original_source_url ? (
              <a className="secondary-button" href={entry.original_source_url} target="_blank" rel="noreferrer">
                <ExternalLink size={15} aria-hidden="true" />
                <span>Open original public source</span>
              </a>
            ) : null}
            {source.data ? (
              <a className="secondary-button" href={source.data.url} target="_blank" rel="noreferrer">
                <ExternalLink size={15} aria-hidden="true" />
                <span>Open retained source evidence</span>
              </a>
            ) : null}
            {canWriteWorkspace(workspace.role) ? <RenameKnowledge entry={entry} onSaved={saved} /> : null}
            {canWriteWorkspace(workspace.role) ? (
              <DeleteAction
                kind="knowledge"
                workspaceId={workspace.id}
                id={entry.id}
                name={entry.name}
                disabled={busy}
                onDeleted={() => navigate("/knowledge/review")}
              />
            ) : null}
          </div>
        }
      />

      {state.isError ? (
        <p className="inline-note" role="alert">
          Could not refresh knowledge. Showing the last loaded data.{" "}
          <Button variant="ghost" size="sm" onClick={() => void state.refetch()}>Try again</Button>
        </p>
      ) : null}

      {source.isError ? (
        <p className="form-error" role="alert">
          Could not open retained source evidence.{" "}
          <Button variant="ghost" size="sm" onClick={() => void source.refetch()}>Try again</Button>
        </p>
      ) : null}

      <div
        className="knowledge-meta-strip"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "16px",
          flexWrap: "wrap",
          marginBottom: "20px",
        }}
      >
        <p className="muted" style={{ margin: 0 }}>
          Source purpose:{" "}
          <strong style={{ color: "var(--text)" }}>
            {entry.roles.map((role) => sourceRoles.find(([value]) => value === role)?.[1] ?? role).join(", ")}
          </strong>
        </p>
        <span className="status-badge status-neutral" style={{ fontSize: "11px", padding: "1px 7px" }}>
          {isLink ? "Public Link" : "Document"}
        </span>
      </div>

      {pending ? (
        <section className="panel section-block">
          <div className="section-heading">
            <h2>Ingestion in progress</h2>
            <span className="status-badge status-warning">In progress</span>
          </div>
          <IngestionProgress entry={entry} />
          <div
            className="stage-ledger"
            style={{
              display: "grid",
              gap: "10px",
              margin: "20px 0",
              padding: "16px",
              background: "var(--surface-muted)",
              borderRadius: "8px",
              border: "1px solid var(--border)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--success)" }}>
              <CheckCircle2 size={16} />
              <span><strong>Stage 1:</strong> Source saved</span>
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                color: entry.processing_status === "processing" ? "var(--primary)" : "var(--text-3)",
              }}
            >
              {entry.processing_status === "processing" ? <Spinner /> : <Clock size={16} />}
              <span>
                <strong>Stage 2:</strong>{" "}
                {entry.processing_stage ? ingestionStageLabel(entry)
                  : entry.processing_status === "processing" ? "Processing source" : "Queued for processing"}
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--text-3)" }}>
              <FileCheck size={16} />
              <span><strong>Stage 3:</strong> Awaiting generated knowledge for review</span>
            </div>
          </div>
          <p className="muted">You can leave this page. Processing will continue, and the knowledge will appear here when ready.</p>
        </section>
      ) : failed ? (
        <section className="panel section-block">
          <div className="section-heading">
            <h2>Processing failed</h2>
            <span className="status-badge status-danger">Failed</span>
          </div>
          <p className="form-error" role="alert">{entry.processing_error || "Knowledge processing failed."}</p>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <p className="muted" style={{ margin: "12px 0 16px" }}>
            The source could not be converted into testable knowledge. Check that the source is readable and matches the supported formats, or try again.
          </p>
          {canWriteWorkspace(workspace.role) ? (
            <Button variant="secondary" disabled={busy} onClick={() => void retry()}>
              {busy ? "Retrying…" : "Retry processing"}
            </Button>
          ) : null}
        </section>
      ) : (
        <div className="knowledge-review-layout">
          <KnowledgeResult preview={entry.preview} />
          <aside className="knowledge-review-rail" aria-label="Knowledge approval and applications">
            {isApproved ? (
              <>
                <div
                  className="panel"
                  style={{
                    display: "grid",
                    gap: "12px",
                    marginBottom: "20px",
                    padding: "20px",
                    border: "1px solid var(--border)",
                    borderRadius: "8px",
                    background: "var(--surface)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <h2 style={{ margin: 0, fontSize: "16px" }}>Knowledge Status</h2>
                    <span className="status-badge status-success">Available for tests</span>
                  </div>
                  <p className="knowledge-approved-status" style={{ margin: 0, fontSize: "13px", color: "var(--text-2)" }}>
                    This knowledge set has been approved and is available for inclusion in test runs across your workspace.
                  </p>
                </div>
                <KnowledgeApplications
                  key={`${entry.id}:${entry.application_ids?.join()}`}
                  entry={entry}
                  onSaved={saved}
                />
              </>
            ) : canWriteWorkspace(workspace.role) ? (
              <section className="panel form-grid knowledge-approval">
                <h2>Approve for use in tests</h2>
                <p className="muted">Check each item against the original source before approving.</p>
                <div
                  className="review-checklist"
                  style={{
                    margin: "8px 0 12px",
                    padding: "12px",
                    background: "var(--surface-muted)",
                    borderRadius: "6px",
                    border: "1px solid var(--border)",
                    fontSize: "13px",
                    display: "grid",
                    gap: "8px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      color: hasKnowledge ? "var(--success)" : "var(--text-3)",
                    }}
                  >
                    <CheckCircle2 size={16} />
                    <span>Extracted items: {entry.knowledge_count + entry.artifact_count + entry.skill_count} ready</span>
                  </div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      color: entry.issue_count === 0 ? "var(--success)" : "var(--warning)",
                    }}
                  >
                    <ShieldCheck size={16} />
                    <span>Extraction issues: {entry.issue_count} recorded</span>
                  </div>
                </div>
                <label className="knowledge-confirmation">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(event) => setConfirmedFor(event.target.checked ? reviewKey : null)}
                    disabled={busy || !hasKnowledge}
                  />
                  <span>I reviewed this knowledge against its source and confirmed the source purpose.</span>
                </label>
                {error ? <p className="form-error" role="alert">{error}</p> : null}
                {!hasKnowledge ? <p className="form-note">This source produced no knowledge to approve.</p> : null}
                <div className="form-actions">
                  <Button disabled={!confirmed || busy || !hasKnowledge} onClick={() => void approve()}>
                    {busy ? <><Spinner /> Approving…</> : "Approve knowledge"}
                  </Button>
                </div>
              </section>
            ) : (
              <p className="muted">Your workspace role can review this set. Write access is required to approve it.</p>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

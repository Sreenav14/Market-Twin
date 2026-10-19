import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Globe, Info } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import { Button } from "../../components/ui/button";
import { EmptyState, ErrorPanel, LoadingPanel, Spinner } from "../../components/ui/StateViews";
import { api } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { type AppShellContext } from "../../layouts/AppShell";
import { IngestionProgress, isIngestionPending } from "./IngestionProgress";

export const sourceRoles = [
  ["product_knowledge", "Product knowledge"],
  ["business_rules", "Business rules"],
  ["demonstration", "Demonstration"],
  ["safety_policy", "Safety policy"],
  ["test_input", "Test input"],
  ["ground_truth", "Expected results"],
  ["ui_reference", "UI reference"],
  ["persona_evidence", "Audience and personas"],
  ["environment_configuration", "Environment configuration"],
] as const;

export function IngestionPage() {
  const { workspace, user } = useOutletContext<AppShellContext>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [file, setFile] = useState<File | null>(null);
  const [sourceType, setSourceType] = useState("file");
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sources = useQuery({
    queryKey: ["ingestion", user.id, workspace.id],
    queryFn: () => api.listIngestion(workspace.id),
    refetchInterval: (query) => query.state.data?.some(isIngestionPending) ? 1500 : false,
  });
  const canWrite = canWriteWorkspace(workspace.role);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if ((sourceType === "file" ? !file : !url.trim()) || !name.trim() || !role || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = sourceType === "link"
        ? await api.ingestKnowledgeLink(workspace.id, url.trim(), name.trim(), [role])
        : await api.ingestKnowledge(workspace.id, file!, name.trim(), [role]);
      queryClient.setQueryData(["knowledge-review", user.id, workspace.id, result.id], result);
      void queryClient.invalidateQueries({ queryKey: ["ingestion", user.id, workspace.id] });
      if (mounted.current) navigate(`/knowledge/review/${result.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not ingest this source.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Ingestion"
        description="Upload a file or research a public link to generate draft knowledge and skills. Review and approve them before using them in a test."
      />
      {canWrite ? (
        <form className="panel form-grid form-card" onSubmit={(event) => void submit(event)} aria-busy={busy}>
          <h2>Ingest knowledge</h2>

          <div className="source-choice-group">
            <span className="field-label" id="source-type-label">Source type</span>
            <div
              className="segmented-control"
              role="tablist"
              aria-labelledby="source-type-label"
              onKeyDown={(event) => {
                if (busy) return;
                const next = event.key === "Home" ? "file" : event.key === "End" ? "link"
                  : ["ArrowLeft", "ArrowRight"].includes(event.key)
                    ? sourceType === "file" ? "link" : "file" : null;
                if (!next) return;
                event.preventDefault();
                setSourceType(next);
                setError(null);
                event.currentTarget.querySelector<HTMLButtonElement>(`#tab-${next}`)?.focus();
              }}
              style={{
                display: "flex",
                gap: "8px",
                margin: "8px 0 16px",
                padding: "4px",
                background: "var(--surface-muted)",
                borderRadius: "8px",
                border: "1px solid var(--border)",
              }}
            >
              <button
                type="button"
                role="tab"
                id="tab-file"
                aria-selected={sourceType === "file"}
                aria-controls="source-panel"
                tabIndex={sourceType === "file" ? 0 : -1}
                className={`segmented-control-item ${sourceType === "file" ? "active" : ""}`}
                style={{
                  flex: "1 1 0",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "8px",
                  minHeight: "40px",
                  padding: "8px 16px",
                  borderRadius: "6px",
                  fontSize: "14px",
                  fontWeight: 600,
                  cursor: "pointer",
                  border: "1px solid",
                  borderColor: sourceType === "file" ? "var(--border-strong)" : "transparent",
                  background: sourceType === "file" ? "var(--surface)" : "transparent",
                  color: sourceType === "file" ? "var(--text)" : "var(--text-3)",
                  boxShadow: sourceType === "file" ? "var(--shadow)" : "none",
                  transition: "all 140ms ease",
                }}
                onClick={() => { setSourceType("file"); setError(null); }}
                disabled={busy}
              >
                <FileText size={16} aria-hidden="true" />
                <span>Upload a file</span>
              </button>
              <button
                type="button"
                role="tab"
                id="tab-link"
                aria-selected={sourceType === "link"}
                aria-controls="source-panel"
                tabIndex={sourceType === "link" ? 0 : -1}
                className={`segmented-control-item ${sourceType === "link" ? "active" : ""}`}
                style={{
                  flex: "1 1 0",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "8px",
                  minHeight: "40px",
                  padding: "8px 16px",
                  borderRadius: "6px",
                  fontSize: "14px",
                  fontWeight: 600,
                  cursor: "pointer",
                  border: "1px solid",
                  borderColor: sourceType === "link" ? "var(--border-strong)" : "transparent",
                  background: sourceType === "link" ? "var(--surface)" : "transparent",
                  color: sourceType === "link" ? "var(--text)" : "var(--text-3)",
                  boxShadow: sourceType === "link" ? "var(--shadow)" : "none",
                  transition: "all 140ms ease",
                }}
                onClick={() => { setSourceType("link"); setError(null); }}
                disabled={busy}
              >
                <Globe size={16} aria-hidden="true" />
                <span>Research a link</span>
              </button>
            </div>
          </div>

          {sourceType === "link" ? (
            <div role="tabpanel" id="source-panel" aria-labelledby="tab-link" className="form-grid">
              <label className="field-label" htmlFor="source-url">Public source link</label>
              <input
                key="source-url"
                id="source-url"
                type="url"
                className="text-input"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://example.com/docs"
                maxLength={2048}
                required
                disabled={busy}
                aria-describedby="link-help"
              />
              <div
                className="info-card"
                id="link-help"
                style={{
                  marginTop: "8px",
                  padding: "12px 14px",
                  borderRadius: "8px",
                  background: "var(--surface-muted)",
                  border: "1px solid var(--border)",
                }}
              >
                <strong style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", color: "var(--text)" }}>
                  <Info size={15} aria-hidden="true" style={{ color: "var(--evidence)" }} />
                  Public Link Research Constraints
                </strong>
                <p className="form-help" style={{ margin: "6px 0 0", fontSize: "13px", lineHeight: "1.6" }}>
                  MarketTwin saves the link immediately, then researches it in the background. It follows connected public pages and expands menus, tabs and readable sections, up to 100 pages or 20 minutes. You can leave the page. Login, form submissions and private pages require a separate approved source.
                </p>
                <ul style={{ margin: "8px 0 0", paddingLeft: "18px", fontSize: "12px", color: "var(--text-3)", lineHeight: "1.6" }}>
                  <li>Public, permitted, read-only HTTP or HTTPS pages only (standard ports 80/443).</li>
                  <li>Destructive actions, form submissions, login/payment, and private network addresses are not supported.</li>
                  <li>Saves source with a durable entry immediately (HTTP 202) and continues in background.</li>
                </ul>
              </div>
            </div>
          ) : (
            <div role="tabpanel" id="source-panel" aria-labelledby="tab-file" className="form-grid">
              <label className="field-label" htmlFor="source-file">Source file</label>
              <input
                key="source-file"
                id="source-file"
                type="file"
                disabled={busy}
                required
                onChange={(event) => {
                  const selected = event.target.files?.[0] ?? null;
                  setFile(selected);
                  if (selected && !name) setName(selected.name.replace(/\.[^.]+$/, ""));
                  setError(null);
                }}
                aria-describedby="source-help"
              />
              <div
                className="info-card"
                id="source-help"
                style={{
                  marginTop: "8px",
                  padding: "12px 14px",
                  borderRadius: "8px",
                  background: "var(--surface-muted)",
                  border: "1px solid var(--border)",
                }}
              >
                <strong style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", color: "var(--text)" }}>
                  <Info size={15} aria-hidden="true" style={{ color: "var(--evidence)" }} />
                  File Specifications & Limits
                </strong>
                <p className="form-help" style={{ margin: "6px 0 0", fontSize: "13px", lineHeight: "1.6" }}>
                  Choose one document, image, or video. Processing continues in the background after the upload finishes.
                </p>
                <ul style={{ margin: "8px 0 0", paddingLeft: "18px", fontSize: "12px", color: "var(--text-3)", lineHeight: "1.6" }}>
                  <li>Maximum file size: 50 MB based on backend configuration.</li>
                  <li>Supported formats: Documents (PDF, Markdown, TXT), Images (PNG, JPEG, WebP), and Media (MP4, WebM).</li>
                  <li>One file per ingestion entry. Large multi-file suites should be uploaded individually.</li>
                </ul>
              </div>
            </div>
          )}

          <label className="field-label" htmlFor="knowledge-name">Knowledge set name</label>
          <input
            id="knowledge-name"
            className="text-input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={200}
            required
            disabled={busy}
          />

          <label className="field-label" htmlFor="source-role">Source purpose</label>
          <select id="source-role" value={role} onChange={(event) => setRole(event.target.value)} required disabled={busy}>
            <option value="">Choose a purpose</option>
            {sourceRoles.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
          </select>
          <p className="form-help">This helps MarketTwin understand how to use the source. You’ll confirm it during review.</p>

          {error ? <p className="form-error" role="alert">{error}</p> : null}
          {busy ? (
            <p className="form-note" role="status">
              {sourceType === "link" ? "Saving the link. Research continues on the review page." : "Uploading source."} Knowledge and skill generation will continue in the background.
            </p>
          ) : null}

          <div className="form-actions">
            <Button type="submit" disabled={(sourceType === "file" ? !file : !url.trim()) || !name.trim() || !role || busy}>
              {busy ? <><Spinner /> Saving source…</> : "Ingest knowledge"}
            </Button>
          </div>
        </form>
      ) : (
        <EmptyState title="Read-only workspace" copy="Your role can review knowledge. Write access is required to ingest sources." />
      )}

      <section className="section-block" aria-labelledby="sources-heading">
        <div className="section-heading">
          <h2 id="sources-heading">Sources</h2>
          <Link className="text-link" to="/knowledge/review">Review knowledge</Link>
        </div>
        {sources.isPending ? (
          <LoadingPanel label="Loading sources" />
        ) : sources.isError ? (
          <ErrorPanel message={sources.error.message} action={<Button variant="secondary" onClick={() => void sources.refetch()}>Try again</Button>} />
        ) : sources.data.length ? (
          <div className="data-list">
            {sources.data.map((source) => (
              <div className="data-row knowledge-list-row" key={source.id}>
                <span className="row-icon" aria-hidden="true">
                  {source.source_name.endsWith("-link.txt") || source.source_name.startsWith("http://") || source.source_name.startsWith("https://") ? (
                    <Globe size={18} />
                  ) : (
                    <FileText size={18} />
                  )}
                </span>
                <div className="row-primary">
                  <strong>{source.name}</strong>
                  <span>{source.source_name}</span>
                </div>
                <div className="knowledge-row-actions">
                  <IngestionProgress entry={source} />
                  <Link className="text-link" to={`/knowledge/review/${source.id}`}>
                    Review<span className="visually-hidden"> {source.name}</span>
                  </Link>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No sources yet" copy="Ingest a source to generate knowledge for review. Approved knowledge can be reused in tests across your workspace." />
        )}
      </section>
    </>
  );
}

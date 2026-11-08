import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Globe, Info } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Button } from "../../components/ui/button";
import { EmptyState, ErrorPanel, LoadingPanel, Spinner } from "../../components/ui/StateViews";
import { ErrorSummary, FieldError, RequiredLegend, RequiredMark } from "../../components/ui/Field";
import { FileDropZone } from "../../components/ui/FileUploader";
import { InlineAlert } from "../../components/ui/Feedback";
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
  ["persona_evidence", "Audience and testers"],
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
  // Punish late, reward early (Spec 3 §6.2): field errors show on blur
  // or submit and clear instantly once fixed (derived from values).
  const [touched, setTouched] = useState<ReadonlySet<string>>(new Set());
  const [submitted, setSubmitted] = useState(false);
  const blur = (field: string) => setTouched((prev) => new Set(prev).add(field));
  const show = (field: string) => submitted || touched.has(field);
  const urlError = sourceType === "link" && show("url")
    ? (!url.trim()
      ? "Enter a public source link, for example https://example.com/docs."
      : !/^https?:\/\//i.test(url.trim())
        ? "Enter a link starting with http:// or https://."
        : null)
    : null;
  const [dropError, setDropError] = useState<string | null>(null);
  const fileError = sourceType === "file"
    ? (dropError ?? (show("file") && !file ? "Select a source file to upload." : null))
    : null;
  const nameError = show("name") && !name.trim() ? "Enter a knowledge set name." : null;
  const roleError = show("role") && !role ? "Choose a source purpose." : null;
  const summaryErrors = [
    ...(sourceType === "file" && fileError ? [{ targetId: "source-file", message: fileError }] : []),
    ...(sourceType === "link" && urlError ? [{ targetId: "source-url", message: urlError }] : []),
    ...(!name.trim() ? [{ targetId: "knowledge-name", message: "Enter a knowledge set name." }] : []),
    ...(!role ? [{ targetId: "source-role", message: "Choose a source purpose." }] : []),
  ];
  const sources = useQuery({
    queryKey: ["ingestion", user.id, workspace.id],
    queryFn: () => api.listIngestion(workspace.id),
    refetchInterval: (query) => query.state.data?.some(isIngestionPending) ? 1500 : false,
  });
  const canWrite = canWriteWorkspace(workspace.role);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    if ((sourceType === "file" ? !file : !url.trim() || urlError) || !name.trim() || !role || busy) return;
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
    <div className="knowledge-ingestion">
      <PageHeader
        title="Add knowledge"
        description="Upload a file or research a public link to generate draft knowledge and skills. Review and approve them before using them in a test."
      />
      {canWrite ? (
        <form className="panel form-grid form-card" onSubmit={(event) => void submit(event)} aria-busy={busy} noValidate>
          <h2>Add a source</h2>
          {submitted && summaryErrors.length ? <ErrorSummary errors={summaryErrors} /> : null}
          <RequiredLegend />

          <div className="source-choice-group">
            <span className="field-label" id="source-type-label">Source type</span>
            <SegmentedControl
              label="Source type"
              size="lg"
              disabled={busy}
              options={[
                { value: "file", label: (<><FileText size={16} aria-hidden="true" /><span>Upload a file</span></>) },
                { value: "link", label: (<><Globe size={16} aria-hidden="true" /><span>Research a link</span></>) },
              ]}
              value={sourceType}
              onChange={(next) => { setSourceType(next); setError(null); }}
            />          </div>

          {sourceType === "link" ? (
            <div className="form-grid">
              <label className="field-label" htmlFor="source-url">Public source link <RequiredMark required /></label>
              <input
                key="source-url"
                id="source-url"
                type="url"
                className="text-input"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                onBlur={() => blur("url")}
                placeholder="https://example.com/docs"
                maxLength={2048}
                required
                disabled={busy}
                aria-invalid={urlError ? true : undefined}
                aria-describedby={urlError ? "link-help source-url-error" : "link-help"}
              />
              {urlError ? <FieldError id="source-url-error">{urlError}</FieldError> : null}
              <div
                className="info-card info-card-flat"
                id="link-help"
              >
                <strong className="info-card-title">
                  <Info size={16} aria-hidden="true" />
                  Public Link Research Constraints
                </strong>
                <p className="form-help">
                  MarketTwin saves the link immediately, then researches it in the background. It follows connected public pages and expands menus, tabs and readable sections, up to 100 pages or 20 minutes. You can leave the page. Login, form submissions and private pages require a separate approved source.
                </p>
                <ul className="info-card-list">
                  <li>Public, permitted, read-only HTTP or HTTPS pages only (standard ports 80/443).</li>
                  <li>Destructive actions, form submissions, login/payment, and private network addresses are not supported.</li>
                  <li>Saves source with a durable entry immediately (HTTP 202) and continues in background.</li>
                </ul>
              </div>
            </div>
          ) : (
            <div className="form-grid">
              <label className="field-label" htmlFor="source-file">Source file <RequiredMark required /></label>
              <FileDropZone
                id="source-file"
                disabled={busy}
                file={file}
                invalid={Boolean(fileError)}
                describedBy={fileError ? "source-file-constraints source-file-error" : "source-file-constraints"}
                onPick={(selected) => {
                  setFile(selected);
                  setDropError(null);
                  if (!name) setName(selected.name.replace(/\.[^.]+$/, ""));
                  setError(null);
                }}
                onInvalid={(message) => setDropError(message)}
                onRemove={() => { setFile(null); setDropError(null); }}
              />
              {fileError ? <FieldError id="source-file-error">{fileError}</FieldError> : null}
              <p className="form-help">
                Choose one document, image, or video. Processing continues in the background after the upload finishes.
              </p>
            </div>
          )}

          <label className="field-label" htmlFor="knowledge-name">Knowledge set name <RequiredMark required /></label>
          <input
            id="knowledge-name"
            className="text-input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            onBlur={() => blur("name")}
            maxLength={200}
            required
            disabled={busy}
            aria-invalid={nameError ? true : undefined}
            aria-describedby={nameError ? "knowledge-name-error" : undefined}
          />
          {nameError ? <FieldError id="knowledge-name-error">{nameError}</FieldError> : null}

          <label className="field-label" htmlFor="source-role">Source purpose <RequiredMark required /></label>
          <select id="source-role" value={role} onChange={(event) => setRole(event.target.value)} onBlur={() => blur("role")} required disabled={busy} aria-invalid={roleError ? true : undefined} aria-describedby={roleError ? "source-role-help source-role-error" : "source-role-help"}>
            <option value="">Choose a purpose</option>
            {sourceRoles.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
          </select>
          <p className="form-help" id="source-role-help">This helps MarketTwin understand how to use the source. You’ll confirm it during review.</p>
          {roleError ? <FieldError id="source-role-error">{roleError}</FieldError> : null}

          {error ? <InlineAlert severity="error" title="Could not add this source" role="alert">{error}</InlineAlert> : null}
          {busy ? (
            <p className="form-note" role="status">
              {sourceType === "link" ? "Saving the link. Research continues on the review page." : "Uploading source."} Knowledge and skill generation will continue in the background.
            </p>
          ) : null}

          <div className="form-actions">
            <Button type="submit" disabled={busy}>
              {busy ? <><Spinner /> Saving source…</> : "Add knowledge"}
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
                    <Globe size={20} />
                  ) : (
                    <FileText size={20} />
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
    </div>
  );
}

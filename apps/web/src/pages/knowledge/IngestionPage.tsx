import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
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
    if (!file || !name.trim() || !role || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.ingestKnowledge(workspace.id, file, name.trim(), [role]);
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
      <PageHeader title="Ingestion" description="Add source material to your workspace, then review the knowledge it produces." />
      {canWrite ? (
        <form className="panel form-grid form-card" onSubmit={(event) => void submit(event)} aria-busy={busy}>
          <h2>Ingest knowledge</h2>
          <label className="field-label" htmlFor="source-file">Source file</label>
          <input id="source-file" type="file" disabled={busy} required onChange={(event) => {
            const selected = event.target.files?.[0] ?? null;
            setFile(selected);
            if (selected && !name) setName(selected.name.replace(/\.[^.]+$/, ""));
            setError(null);
          }} aria-describedby="source-help" />
          <p className="form-help" id="source-help">Choose one document, image, or video. You can add more sources after this one.</p>
          <label className="field-label" htmlFor="knowledge-name">Knowledge set name</label>
          <input id="knowledge-name" className="text-input" value={name} onChange={(event) => setName(event.target.value)} maxLength={200} required disabled={busy} />
          <label className="field-label" htmlFor="source-role">Source purpose</label>
          <select id="source-role" value={role} onChange={(event) => setRole(event.target.value)} required disabled={busy}>
            <option value="">Choose a purpose</option>
            {sourceRoles.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
          </select>
          <p className="form-help">This helps MarketTwin understand how to use the source. You’ll confirm it during review.</p>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          {busy ? <p className="form-note" role="status">Uploading source. Knowledge processing will continue in the background.</p> : null}
          <div className="form-actions">
            <Button type="submit" disabled={!file || !name.trim() || !role || busy}>
              {busy ? <><Spinner /> Uploading source…</> : "Ingest knowledge"}
            </Button>
          </div>
        </form>
      ) : <EmptyState title="Read-only workspace" copy="Your role can review knowledge. Write access is required to ingest sources." />}
      <section className="section-block" aria-labelledby="sources-heading">
        <div className="section-heading"><h2 id="sources-heading">Sources</h2><Link className="text-link" to="/knowledge/review">Review knowledge</Link></div>
        {sources.isPending ? <LoadingPanel label="Loading sources" /> : sources.isError ? (
          <ErrorPanel message={sources.error.message} action={<Button variant="secondary" onClick={() => void sources.refetch()}>Try again</Button>} />
        ) : sources.data.length ? (
          <div className="data-list">{sources.data.map((source) => (
            <div className="data-row knowledge-list-row" key={source.id}>
              <span className="row-icon" aria-hidden="true"><FileText size={18} /></span>
              <div className="row-primary"><strong>{source.name}</strong><span>{source.source_name}</span></div>
              <div className="knowledge-row-actions">
              <IngestionProgress entry={source} />
              <Link className="text-link" to={`/knowledge/review/${source.id}`}>Review<span className="visually-hidden"> {source.name}</span></Link>
              </div>
            </div>
          ))}</div>
        ) : <EmptyState title="No sources yet" copy="Ingest a source to generate knowledge for review. Approved knowledge can be reused in tests across your workspace." />}
      </section>
    </>
  );
}

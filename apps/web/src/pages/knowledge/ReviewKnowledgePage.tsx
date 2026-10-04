import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { DeleteAction } from "../../components/markettwin/DeleteAction";
import { PageHeader } from "../../components/ui/PageHeader";
import { Button } from "../../components/ui/button";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { api } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { type AppShellContext } from "../../layouts/AppShell";
import { IngestionProgress, isIngestionPending } from "./IngestionProgress";

export function ReviewKnowledgePage() {
  const { workspace, user } = useOutletContext<AppShellContext>();
  const state = useQuery({ queryKey: ["ingestion", user.id, workspace.id], queryFn: () => api.listIngestion(workspace.id), refetchInterval: (query) => query.state.data?.some(isIngestionPending) ? 1500 : false });
  return (
    <>
      <PageHeader title="Review knowledge" description="Check generated knowledge against its source before making it available to tests." action={<Link className="secondary-button" to="/ingestion">Ingest knowledge</Link>} />
      {state.isPending ? <LoadingPanel label="Loading knowledge" /> : state.isError ? (
        <ErrorPanel message={state.error.message} action={<Button variant="secondary" onClick={() => void state.refetch()}>Try again</Button>} />
      ) : state.data.length ? (
        <div className="data-list">{[...state.data].sort((a, b) => Number(a.status === "approved") - Number(b.status === "approved")).map((entry) => (
          <div className="data-row knowledge-list-row" key={entry.id}>
            <span className="row-icon" aria-hidden="true"><FileText size={18} /></span>
            <div className="row-primary"><strong>{entry.name}</strong>{isIngestionPending(entry) || entry.processing_status === "failed" ? <span>{entry.source_name}</span> : <span>{entry.knowledge_count} knowledge items · {entry.artifact_count} artifacts · {entry.skill_count} Skills{entry.issue_count ? ` · ${entry.issue_count} extraction issues` : ""}</span>}</div>
            <div className="knowledge-row-actions">
            <IngestionProgress entry={entry} />
            <Link className="text-link" aria-label={`${entry.status === "approved" ? "View" : "Review"} ${entry.name}`} to={`/knowledge/review/${entry.id}`}>{entry.status === "approved" ? "View" : "Review"}<span className="visually-hidden"> {entry.name}</span></Link>
            {canWriteWorkspace(workspace.role) ? <DeleteAction kind="knowledge" workspaceId={workspace.id} id={entry.id} name={entry.name} onDeleted={() => void state.refetch()} /> : null}
            </div>
          </div>
        ))}</div>
      ) : <EmptyState title="No knowledge to review" copy="Ingest a source first. Its generated knowledge will appear here for review." action={<Link className="primary-button" to="/ingestion">Ingest knowledge</Link>} />}
    </>
  );
}

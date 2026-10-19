import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileText, Globe, Search, X } from "lucide-react";
import { DeleteAction } from "../../components/markettwin/DeleteAction";
import { PageHeader } from "../../components/ui/PageHeader";
import { Button } from "../../components/ui/button";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { api } from "../../lib/api";
import { canWriteWorkspace } from "../../lib/permissions";
import { type AppShellContext } from "../../layouts/AppShell";
import { IngestionProgress, isIngestionPending } from "./IngestionProgress";
import { sourceRoles } from "./IngestionPage";

export function ReviewKnowledgePage() {
  const { workspace, user } = useOutletContext<AppShellContext>();
  const [params, setParams] = useSearchParams();
  const search = params.get("q") || "";
  const status = params.get("status") || "all";

  const state = useQuery({
    queryKey: ["ingestion", user.id, workspace.id],
    queryFn: () => api.listIngestion(workspace.id),
    refetchInterval: (query) => query.state.data?.some(isIngestionPending) ? 1500 : false,
  });

  const applications = useQuery({
    queryKey: ["applications", user.id, workspace.id],
    queryFn: () => api.listApplications(workspace.id),
  });

  const appMap = new Map((applications.data ?? []).map((app) => [app.id, app.name]));

  const entries = (state.data ?? [])
    .filter((entry) => {
      const entryStatus = isIngestionPending(entry)
        ? "pending"
        : entry.processing_status === "failed"
        ? "failed"
        : entry.status;
      return (
        (status === "all" || status === entryStatus) &&
        `${entry.name} ${entry.source_name}`.toLowerCase().includes(search.toLowerCase())
      );
    })
    .sort(
      (a, b) =>
        Number(a.status === "approved") - Number(b.status === "approved") ||
        b.created_at.localeCompare(a.created_at),
    );

  function filter(key: string, value: string) {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (!value || value === "all") next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true },
    );
  }

  const isFiltered = Boolean(search.trim() || status !== "all");
  const statusLabel =
    status === "draft"
      ? "Needs review"
      : status === "approved"
      ? "Approved"
      : status === "pending"
      ? "In progress"
      : status === "failed"
      ? "Processing failed"
      : "";

  return (
    <div className="knowledge-library">
      <PageHeader
        title="Review knowledge"
        description="Check generated items against the source, approve the set, then attach it to an application for test selection."
        action={<Link className="secondary-button" to="/ingestion">Ingest knowledge</Link>}
      />

      {state.isPending ? (
        <LoadingPanel label="Loading knowledge" />
      ) : !state.data ? (
        <ErrorPanel
          message={state.error?.message || "Could not load knowledge."}
          action={<Button variant="secondary" onClick={() => void state.refetch()}>Try again</Button>}
        />
      ) : state.data.length ? (
        <>
          {state.isError ? (
            <p className="inline-note" role="alert">
              Could not refresh knowledge. Showing the last loaded data.{" "}
              <Button variant="ghost" size="sm" onClick={() => void state.refetch()}>Try again</Button>
            </p>
          ) : null}

          <div className="filter-bar">
            <div className="search-field">
              <Search size={17} aria-hidden="true" />
              <input
                aria-label="Search knowledge"
                placeholder="Find a knowledge set or source…"
                value={search}
                onChange={(event) => filter("q", event.target.value)}
              />
            </div>
            <select
              className="text-input filter-control"
              aria-label="Knowledge status"
              value={status}
              onChange={(event) => filter("status", event.target.value)}
            >
              <option value="all">All statuses</option>
              <option value="draft">Needs review</option>
              <option value="approved">Approved</option>
              <option value="pending">In progress</option>
              <option value="failed">Processing failed</option>
            </select>
          </div>

          <div
            className="filter-summary-row"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "8px",
              margin: "-4px 0 14px",
            }}
          >
            <p className="knowledge-list-count muted" aria-live="polite" style={{ margin: 0 }}>
              {entries.length} of {state.data.length} knowledge sets
            </p>
            {isFiltered ? (
              <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                <span className="muted" style={{ fontSize: "12px" }}>Active filters:</span>
                {search ? (
                  <span className="status-badge status-neutral" style={{ fontSize: "11px", gap: "4px" }}>
                    "{search}"
                  </span>
                ) : null}
                {status !== "all" ? (
                  <span className="status-badge status-neutral" style={{ fontSize: "11px" }}>
                    {statusLabel}
                  </span>
                ) : null}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setParams({})}
                  style={{ fontSize: "12px", height: "26px", padding: "0 6px" }}
                >
                  <X size={13} aria-hidden="true" />
                  <span>Clear</span>
                </Button>
              </div>
            ) : null}
          </div>

          {entries.length ? (
            <div className="data-list" role="list">
              {entries.map((entry) => {
                const isLink = Boolean(entry.original_source_url) ||
                  entry.source_name.endsWith("-link.txt") ||
                  entry.source_name.startsWith("http://") ||
                  entry.source_name.startsWith("https://");
                const hasAssignedApps = Boolean(entry.application_ids?.length);

                return (
                  <div className="data-row knowledge-list-row" key={entry.id} role="listitem">
                    <span className="row-icon" aria-hidden="true">
                      {isLink ? <Globe size={18} /> : <FileText size={18} />}
                    </span>
                    <div className="row-primary">
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                        <strong>
                          <Link to={`/knowledge/review/${entry.id}`}>{entry.name}</Link>
                        </strong>
                        <span
                          className="status-badge status-neutral"
                          style={{ fontSize: "11px", padding: "1px 7px" }}
                        >
                          {isLink ? "Public Link" : "Document"}
                        </span>
                      </div>
                      <span>
                        {entry.source_name} · Purpose:{" "}
                        {entry.roles
                          .map((role) => sourceRoles.find(([val]) => val === role)?.[1] ?? role)
                          .join(", ")}
                      </span>
                      {isIngestionPending(entry) || entry.processing_status === "failed" ? null : (
                        <span>
                          {[
                            entry.knowledge_count
                              ? `${entry.knowledge_count} knowledge ${
                                  entry.knowledge_count === 1 ? "item" : "items"
                                }`
                              : "",
                            entry.artifact_count
                              ? `${entry.artifact_count} ${
                                  entry.artifact_count === 1 ? "artifact" : "artifacts"
                                }`
                              : "",
                            entry.skill_count
                              ? `${entry.skill_count} ${entry.skill_count === 1 ? "Skill" : "Skills"}`
                              : "",
                            entry.issue_count
                              ? `${entry.issue_count} extraction ${
                                  entry.issue_count === 1 ? "issue" : "issues"
                                }`
                              : "",
                          ]
                            .filter(Boolean)
                            .join(" · ") || "No generated items"}
                        </span>
                      )}
                      {hasAssignedApps ? (
                        <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap", marginTop: "2px" }}>
                          <span className="muted" style={{ fontSize: "12px" }}>Assigned apps:</span>
                          {entry.application_ids?.map((appId) => (
                            <span
                              key={appId}
                              className="status-badge status-info"
                              style={{ fontSize: "11px", padding: "1px 6px" }}
                            >
                              {appMap.get(appId) || "Application"}
                            </span>
                          ))}
                        </div>
                      ) : entry.status === "approved" ? (
                        <span className="muted" style={{ fontSize: "12px" }}>
                          Not assigned to applications
                        </span>
                      ) : null}
                    </div>
                    <div className="knowledge-row-actions">
                      <IngestionProgress entry={entry} />
                      <Link
                        className="text-link"
                        aria-label={`${entry.status === "approved" ? "View" : "Review"} ${entry.name}`}
                        to={`/knowledge/review/${entry.id}`}
                      >
                        {entry.status === "approved" ? "View" : "Review"}
                        <span className="visually-hidden"> {entry.name}</span>
                      </Link>
                      {canWriteWorkspace(workspace.role) ? (
                        <DeleteAction
                          kind="knowledge"
                          workspaceId={workspace.id}
                          id={entry.id}
                          name={entry.name}
                          onDeleted={() => void state.refetch()}
                        />
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState
              title="No matching knowledge"
              copy="Try another name or status."
              action={<Button variant="secondary" onClick={() => setParams({})}>Clear filters</Button>}
            />
          )}
        </>
      ) : (
        <EmptyState
          title="No knowledge to review"
          copy="Ingest a source first. Its generated knowledge will appear here for review."
          action={
            canWriteWorkspace(workspace.role) ? (
              <Link className="primary-button" to="/ingestion">Ingest knowledge</Link>
            ) : undefined
          }
        />
      )}
    </div>
  );
}

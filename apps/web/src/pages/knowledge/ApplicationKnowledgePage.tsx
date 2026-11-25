import { Link, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "../../components/ui/PageHeader";
import { Button } from "../../components/ui/button";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { api } from "../../lib/api";
import { type AppShellContext } from "../../layouts/AppShell";
import { AppMapPanel } from "../../components/knowledge/AppMapPanel";

export function ApplicationKnowledgePage() {
  const { workspace } = useOutletContext<AppShellContext>();
  const { applicationId } = useParams();
  const [params] = useSearchParams();
  // The map renders for the earliest-created active target (the
  // targets list is returned in creation order; the first active
  // entry wins) — the rule the retired ingestion page used (doc 16
  // section 10.4).
  const targets = useQuery({
    queryKey: ["application-targets", applicationId],
    queryFn: () => api.listTargets(applicationId!),
    enabled: Boolean(applicationId),
  });
  const mapTarget = targets.data
    ? (targets.data.find((target) => target.id === params.get("target"))
      ?? targets.data.find((target) => target.status === "active") ?? targets.data[0])
    : undefined;

  return (
    <div className="knowledge-ingestion">
      <PageHeader
        title="Knowledge"
        description="The application map is observed from the live application. It is the knowledge source test runs plan from."
        action={<Link className="secondary-button" to="/knowledge">Open workspace sources</Link>}
      />
      {targets.isPending ? (
        <LoadingPanel label="Loading targets" />
      ) : targets.isError ? (
        <ErrorPanel message={targets.error.message} action={<Button variant="secondary" onClick={() => void targets.refetch()}>Try again</Button>} />
      ) : mapTarget && applicationId ? (
        <section className="section-block" aria-labelledby="app-map-heading">
          <div className="section-heading">
            <h2 id="app-map-heading">Application map (observed)</h2>
          </div>
          <AppMapPanel workspaceId={workspace.id} applicationId={applicationId} targetId={mapTarget.id} />
        </section>
      ) : (
        <EmptyState title="No targets yet" copy="Add a target for this application before its map can be built." />
      )}
    </div>
  );
}

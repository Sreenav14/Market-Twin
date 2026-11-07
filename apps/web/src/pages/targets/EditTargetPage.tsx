import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { PageHeader } from "../../components/ui/PageHeader";
import { ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { api } from "../../lib/api";

export function EditTargetPage() {
  const { targetId = "" } = useParams();
  const target = useQuery({
    queryKey: ["target", targetId],
    queryFn: () => api.getTarget(targetId),
  });
  if (target.isPending) return <LoadingPanel label="Loading target" />;
  if (target.isError)
    return (
      <ErrorPanel
        message={target.error.message}
        action={
          <button className="secondary-button" onClick={() => void target.refetch()}>
            Try again
          </button>
        }
      />
    );
  const applicationId = target.data.application_id;
  return (
    <>
      <PageHeader
        eyebrow="Target"
        title="Edit target"
        description="Change this target's address or details."
      />
      <section className="panel">
        <h2>Editing targets isn&apos;t available yet</h2>
        <p>
          A target&apos;s address is fixed once it has been authorized, so a
          changed address can&apos;t quietly inherit the old approval. To test
          a different address, add a new target and authorize it.
        </p>
        <div className="button-row">
          <Link className="primary-button" to={`/targets/${targetId}`}>
            Back to the target
          </Link>
          <Link
            className="secondary-button"
            to={`/applications/${applicationId}/targets/new`}
          >
            Add a new target
          </Link>
        </div>
      </section>
    </>
  );
}

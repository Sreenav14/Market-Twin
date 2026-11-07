import { Link, useParams } from "react-router-dom";
import { PageHeader } from "../../components/ui/PageHeader";

export function EditApplicationPage() {
  const { applicationId = "" } = useParams();
  return (
    <>
      <PageHeader
        eyebrow="Application"
        title="Edit app"
        description="Change this app's name or description."
      />
      <section className="panel">
        <h2>Editing apps isn&apos;t available yet</h2>
        <p>
          An app&apos;s name and description can&apos;t be changed after it is
          created. If the details are wrong, add a new app with the right
          details and use it for new tests — the existing app and its tests
          stay as they are.
        </p>
        <div className="button-row">
          <Link className="primary-button" to={`/applications/${applicationId}`}>
            Back to the app
          </Link>
          <Link className="secondary-button" to="/applications/new">
            Add a new app
          </Link>
        </div>
      </section>
    </>
  );
}

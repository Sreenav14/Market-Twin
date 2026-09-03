import { Link } from "react-router-dom";
import { PageHeader } from "../../components/ui/PageHeader";
export function NotFoundPage() { return <><PageHeader eyebrow="404" title="Page not found" description="The resource may not exist, may have moved, or may not be visible to your workspace." /><Link className="secondary-button" to="/overview">Back to overview</Link></>; }

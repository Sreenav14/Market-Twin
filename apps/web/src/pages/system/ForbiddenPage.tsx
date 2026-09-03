import { Link } from "react-router-dom";
import { PageHeader } from "../../components/ui/PageHeader";
export function ForbiddenPage() { return <><PageHeader eyebrow="Access" title="You don’t have permission to open this page." description="MarketTwin permissions are enforced by the Control API. Your frontend role only controls which actions are presented." /><Link className="secondary-button" to="/overview">Back to overview</Link></>; }

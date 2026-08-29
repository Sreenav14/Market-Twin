import { Link } from "react-router-dom";
import { PageHeader } from "../../components/ui/PageHeader";
export function UnexpectedErrorPage() { return <><PageHeader eyebrow="Error" title="Something went wrong" description="MarketTwin could not complete this view. Your saved backend data has not been replaced by a frontend fallback." /><Link className="secondary-button" to="/overview">Back to overview</Link></>; }

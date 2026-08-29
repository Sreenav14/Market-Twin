import { FutureStagePage } from "../../components/ui/FutureStagePage";
import { PageHeader } from "../../components/ui/PageHeader";
export function EditApplicationPage() { return <><PageHeader eyebrow="Application lifecycle" title="Edit application" description="Application editing is reserved in the frontend architecture but is not yet supported by the current Control API." /><FutureStagePage stage="Application lifecycle" title="Edit fields" description="The current Control API does not expose an application update endpoint." /></>; }

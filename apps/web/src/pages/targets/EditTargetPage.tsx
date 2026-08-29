import { FutureStagePage } from "../../components/ui/FutureStagePage";
import { PageHeader } from "../../components/ui/PageHeader";
export function EditTargetPage() { return <><PageHeader eyebrow="Target lifecycle" title="Edit target" description="Target updates must define what happens to authorization and allowed origins before this becomes functional." /><FutureStagePage stage="Target lifecycle" title="Target fields" description="Changing a target URL is security-significant. This page will activate only after the backend defines update and reauthorization semantics." /></>; }

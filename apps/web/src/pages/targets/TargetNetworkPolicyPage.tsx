import { FutureStagePage } from "../../components/ui/FutureStagePage";
import { PageHeader } from "../../components/ui/PageHeader";
export function TargetNetworkPolicyPage() { return <><PageHeader eyebrow="Target network policy" title="Allowed origins" description="MarketTwin keeps browser egress explicit rather than silently allowing every dependency a website requests." /><FutureStagePage stage="Network policy" title="Origin management" description="The browser runtime already enforces allowed origins, but the Control API does not yet expose add/remove-origin management endpoints." /></>; }

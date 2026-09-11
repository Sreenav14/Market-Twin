import { Link } from "react-router-dom";
import { ArrowUpRight, Paperclip, Route } from "lucide-react";
import type { Finding } from "../../lib/api";
import { StatusBadge } from "../ui/StatusBadge";

export function FindingListItem({ finding, runId }: { finding: Finding; runId: string }) {
  const referenceCount = finding.evidence.step_ids.length + finding.evidence.artifact_ids.length;
  return <li className="finding-item"><Link to={`/runs/${runId}/findings/${finding.id}`}>
    <div className="finding-severity"><StatusBadge status={finding.severity} /></div>
    <div className="finding-copy"><span className="category-label">{finding.category.replaceAll("_", " ")}</span><h3>{finding.title}</h3><p>{finding.summary}</p><div className="finding-meta"><span><Route size={14} aria-hidden="true" />{finding.journey_ids.length} affected {finding.journey_ids.length === 1 ? "journey" : "journeys"}</span><span><Paperclip size={14} aria-hidden="true" />{referenceCount} {referenceCount === 1 ? "reference" : "references"}</span></div></div>
    <ArrowUpRight className="finding-arrow" size={19} aria-hidden="true" />
  </Link></li>;
}

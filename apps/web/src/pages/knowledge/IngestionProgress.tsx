import { type IngestionSummary } from "../../lib/api";

export function isIngestionPending(entry: IngestionSummary) {
  return entry.processing_status === "queued" || entry.processing_status === "processing";
}

export function ingestionStageLabel(entry: IngestionSummary) {
  switch (entry.processing_stage) {
    case "queued": return "Source saved · Waiting to process";
    case "researching": return "Researching public pages";
    case "generating": return "Generating knowledge from retained evidence";
    case "review": return "Ready for review";
    case "approved": return "Approved";
    case "failed": return "Processing failed";
    default: return "Processing source";
  }
}

export function IngestionProgress({ entry }: { entry: IngestionSummary }) {
  if (isIngestionPending(entry)) {
    const queued = entry.processing_status === "queued";
    const label = entry.processing_error
      || (entry.processing_stage ? ingestionStageLabel(entry)
        : queued ? "Source saved · Waiting to process" : "Processing source");
    return <div className="ingestion-progress">
      <span role="status">{label}</span>
      <progress aria-label="Ingestion progress" aria-valuetext={label} />
    </div>;
  }
  return <span className={`status-badge ${entry.processing_status === "failed" ? "status-danger" : entry.status === "approved" ? "status-success" : "status-neutral"}`}>
    {entry.processing_status === "failed" ? "Processing failed" : entry.status === "approved" ? "Approved" : "Needs review"}
  </span>;
}

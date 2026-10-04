import { type IngestionSummary } from "../../lib/api";

export function isIngestionPending(entry: IngestionSummary) {
  return entry.processing_status === "queued" || entry.processing_status === "processing";
}

export function IngestionProgress({ entry }: { entry: IngestionSummary }) {
  if (isIngestionPending(entry)) {
    const queued = entry.processing_status === "queued";
    const label = queued ? "Source saved · Waiting to process" : "Generating knowledge";
    return <div className="ingestion-progress">
      <span role="status">{label}</span>
      <progress max={100} value={queued ? 20 : 50} aria-label="Ingestion progress" aria-valuetext={label} />
    </div>;
  }
  return <span className={`status-badge ${entry.processing_status === "failed" ? "status-danger" : entry.status === "approved" ? "status-success" : "status-neutral"}`}>
    {entry.processing_status === "failed" ? "Processing failed" : entry.status === "approved" ? "Approved" : "Needs review"}
  </span>;
}

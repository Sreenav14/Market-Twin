import { type IngestionSummary } from "../../lib/api";
import { StatusPill } from "../../components/ui/StatusBadge";
import { statusEntry } from "../../lib/status";

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
    const stageWord = entry.processing_error ? "Processing failed"
      : statusEntry("lifecycle", entry.processing_stage ?? (queued ? "queued" : "processing")).word;
    return <div className="ingestion-progress">
      <StatusPill tone={entry.processing_error ? "danger" : "info"} glyph={entry.processing_error ? "✕" : "•"}>
        {stageWord}
      </StatusPill>
      {entry.processing_error ? <span role="status">{entry.processing_error}</span> : null}
      <progress aria-label="Ingestion progress" aria-valuetext={label} />
    </div>;
  }
  return <StatusPill
    tone={entry.processing_status === "failed" ? "danger" : entry.status === "approved" ? "success" : "neutral"}
    glyph={entry.processing_status === "failed" ? "✕" : entry.status === "approved" ? "✓" : "!"}
  >
    {entry.processing_status === "failed" ? "Processing failed" : entry.status === "approved" ? "Approved" : "Needs review"}
  </StatusPill>;
}

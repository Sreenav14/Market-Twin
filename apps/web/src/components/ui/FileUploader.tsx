import { useRef, useState } from "react";
import { FileText, Upload, X } from "lucide-react";

/* File drop zone — Phase 2d, Spec 3 §5 (Carbon uploader anatomy).
   Real drag-and-drop + click-to-browse; the browse button is the
   keyboard path, drag is the enhancement (never the only path).

   Accepted formats — read from the ingestion code, not invented:
   the control-api upload endpoint itself enforces NO extension
   allowlist (filename validity, non-empty, and the configured
   50 MB ceiling only); the knowledge worker's extraction
   dispatcher (services/knowledge-worker extraction/dispatcher.py)
   is what a file must survive to be processed, and it accepts
   exactly the extensions below — anything else ends in the
   "unsupported" state. The `accept` attribute and the client-side
   wrong-type error mirror that dispatcher set, and the size check
   mirrors the API's knowledge_preview_max_bytes default. */
export const INGESTION_EXTENSIONS = [
  ".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".csv", ".json",
  ".png", ".jpg", ".jpeg", ".webp",
  ".mp4", ".mov", ".webm",
] as const;
export const INGESTION_ACCEPT = INGESTION_EXTENSIONS.join(",");
export const INGESTION_MAX_BYTES = 50 * 1024 * 1024;
export const INGESTION_CONSTRAINTS =
  "Documents (PDF, DOCX, PPTX, XLSX, TXT, MD, CSV, JSON), images (PNG, JPG, WebP) or video (MP4, MOV, WebM) · Up to 50 MB · One file";

export function validateIngestionFile(file: File): string | null {
  const dot = file.name.lastIndexOf(".");
  const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!(INGESTION_EXTENSIONS as readonly string[]).includes(extension)) {
    return `"${file.name}" is not a supported format. Choose one of the supported formats listed on the drop zone.`;
  }
  if (file.size > INGESTION_MAX_BYTES) {
    return `"${file.name}" is too large. Use a file under 50 MB.`;
  }
  if (file.size === 0) {
    return `"${file.name}" is empty. Choose a file with content.`;
  }
  return null;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileDropZone({
  id,
  disabled = false,
  file,
  invalid = false,
  describedBy,
  onPick,
  onInvalid,
  onRemove,
}: {
  id: string;
  disabled?: boolean;
  file: File | null;
  invalid?: boolean;
  describedBy: string;
  onPick: (file: File) => void;
  onInvalid: (message: string) => void;
  onRemove: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const browseRef = useRef<HTMLButtonElement>(null);
  const [dragging, setDragging] = useState(false);

  function take(candidate: File | null | undefined) {
    if (!candidate) return;
    const problem = validateIngestionFile(candidate);
    if (problem) {
      onInvalid(problem);
      return;
    }
    onPick(candidate);
  }

  return (
    <div>
      <div
        className="dropzone"
        data-dragging={dragging || undefined}
        data-invalid={invalid || undefined}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!disabled) take(event.dataTransfer.files?.[0]);
        }}
      >
        <input
          ref={inputRef}
          id={id}
          type="file"
          className="dropzone-input"
          accept={INGESTION_ACCEPT}
          disabled={disabled}
          required
          tabIndex={-1}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          onChange={(event) => {
            take(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
        <Upload size={24} aria-hidden="true" className="dropzone-icon" />
        <p className="dropzone-primary">
          {dragging ? "Drop the file to select it" : "Drag and drop a file here"}
        </p>
        <p className="dropzone-secondary">
          or{" "}
          <button
            ref={browseRef}
            type="button"
            className="dropzone-browse"
            disabled={disabled}
            onClick={() => inputRef.current?.click()}
          >
            Browse files
          </button>
        </p>
        <p className="dropzone-constraints" id={`${id}-constraints`}>
          {INGESTION_CONSTRAINTS}
        </p>
      </div>
      {file ? (
        <div className="file-row">
          <FileText size={16} aria-hidden="true" />
          <span className="file-row-name" title={file.name}>{file.name}</span>
          <span className="file-row-meta">{formatFileSize(file.size)}</span>
          <button
            type="button"
            className="file-row-remove"
            aria-label={`Remove ${file.name}`}
            disabled={disabled}
            onClick={() => {
              onRemove();
              browseRef.current?.focus();
            }}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      ) : null}
    </div>
  );
}

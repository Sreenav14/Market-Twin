import { useEffect, useState } from "react";
import { InlineAlert } from "../ui/Feedback";
import { api, type ArtifactAccess } from "../../lib/api";

/* Shared evidence loader — Phase 2e. This component lived inside
   FindingDetailPage and was imported FROM that page file by five
   other files; it now lives in the shared layer. The frame it
   renders is the ONE evidence-frame recipe (states.css): frame
   max-width 720px, image max-height 520px, contain, top-left —
   on every surface. Light surfaces stay light; the dark stage
   belongs to the live viewer alone. */
type EvidenceBounds = { x: number; y: number; width: number; height: number };

export function ArtifactEvidence({
  runId, artifactId, autoLoad = false, bounds,
}: { runId: string; artifactId: string; autoLoad?: boolean; bounds?: EvidenceBounds }) {
  return <ArtifactPreview key={`${runId}:${artifactId}`} runId={runId} artifactId={artifactId} autoLoad={autoLoad} bounds={bounds} />;
}

function ArtifactPreview({
  runId,
  artifactId,
  autoLoad = false,
  bounds,
}: {
  runId: string;
  artifactId: string;
  autoLoad?: boolean;
  bounds?: EvidenceBounds;
}) {
  const [access, setAccess] = useState<ArtifactAccess | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  useEffect(() => { if (autoLoad) void loadEvidence(); }, [autoLoad, runId, artifactId]);

  async function loadEvidence() {
    setLoading(true);
    setError(null);
    setAccess(null);
    setSize(null);

    try {
      const result = await api.getArtifactAccess(runId, artifactId);

      setAccess(result);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Evidence could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  }

  const isImage = access?.content_type.startsWith("image/") ?? false;
  const outside = bounds && size && (bounds.x < 0 || bounds.y < 0 ||
    bounds.x + bounds.width > size.width || bounds.y + bounds.height > size.height);

  return (
    <div className="artifact-evidence">
      <button
        type="button"
        className="secondary-button compact"
        onClick={loadEvidence}
        disabled={loading}
      >
        {loading
          ? "Loading evidence…"
          : access
            ? "Refresh evidence"
            : "View evidence"}
      </button>

      {error ? (
        <InlineAlert severity="error" title="Evidence could not be loaded" role="alert">
          {error}
        </InlineAlert>
      ) : null}

      {outside ? <p>No screenshot covers this element — measurements only.</p> : null}
      {access && isImage && !outside ? (
        <a
          className={bounds ? "artifact-preview-link look-evidence-image" : "artifact-preview-link"}
          href={access.url}
          target="_blank"
          rel="noreferrer"
        >
          <img
            className="artifact-preview"
            src={access.url}
            alt={`Recorded ${access.artifact_type} evidence`}
            onLoad={bounds ? event => setSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight }) : undefined}
            onError={() => { setAccess(null); setError("Evidence unavailable. Refresh access to try again."); }}
          />
          {bounds && size && <span className="look-evidence-outline" aria-hidden="true" style={{
            left: `${100 * bounds.x / size.width}%`, top: `${100 * bounds.y / size.height}%`,
            width: `${100 * bounds.width / size.width}%`, height: `${100 * bounds.height / size.height}%`,
          }} />}
        </a>
      ) : null}

      {access && !isImage ? (
        <a
          className="text-link"
          href={access.url}
          target="_blank"
          rel="noreferrer"
        >
          Open artifact
        </a>
      ) : null}
    </div>
  );
}


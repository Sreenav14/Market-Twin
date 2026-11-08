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
export function ArtifactEvidence({
  runId, artifactId, autoLoad = false,
}: { runId: string; artifactId: string; autoLoad?: boolean }) {
  return <ArtifactPreview key={`${runId}:${artifactId}`} runId={runId} artifactId={artifactId} autoLoad={autoLoad} />;
}

function ArtifactPreview({
  runId,
  artifactId,
  autoLoad = false,
}: {
  runId: string;
  artifactId: string;
  autoLoad?: boolean;
}) {
  const [access, setAccess] = useState<ArtifactAccess | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (autoLoad) void loadEvidence(); }, [autoLoad, runId, artifactId]);

  async function loadEvidence() {
    setLoading(true);
    setError(null);
    setAccess(null);

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

      {access && isImage ? (
        <a
          className="artifact-preview-link"
          href={access.url}
          target="_blank"
          rel="noreferrer"
        >
          <img
            className="artifact-preview"
            src={access.url}
            alt={`Recorded ${access.artifact_type} evidence`}
            onError={() => { setAccess(null); setError("Evidence unavailable. Refresh access to try again."); }}
          />
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


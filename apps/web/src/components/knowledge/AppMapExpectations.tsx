import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "../../lib/api";
import { Button } from "../ui/button";
import { StatusPill } from "../ui/StatusBadge";
import type { AppMapAuditLine, AppMapConflictLine, AppMapExpectationLine } from "./AppMapPanel";

export function AppMapExpectations({ base, mapId }: { base: string; mapId: string }) {
  const queryClient = useQueryClient();
  const [probe, setProbe] = useState(false);
  const [ownerText, setOwnerText] = useState<Record<string, string>>({});
  const expectations = useQuery({
    queryKey: ["app-map-expectations", mapId],
    queryFn: () =>
      request<{ items: AppMapExpectationLine[]; gate: Record<string, unknown> }>(
        `${base}/app-maps/${mapId}/expectations`,
      ),
    retry: false,
  });
  const suggestions = useQuery({
    queryKey: ["app-map-suggestions", mapId],
    queryFn: () =>
      request<{ items: AppMapExpectationLine[] }>(
        `${base}/app-maps/${mapId}/expectations/suggestions`,
      ),
    retry: false,
  });
  const conflicts = useQuery({
    queryKey: ["app-map-conflicts", mapId],
    queryFn: () =>
      request<{ items: AppMapConflictLine[] }>(
        `${base}/app-maps/${mapId}/conflicts`,
      ),
    retry: false,
  });
  const audit = useQuery({
    queryKey: ["app-map-audit", mapId],
    queryFn: () =>
      request<AppMapAuditLine>(`${base}/app-map/audits/latest`),
    retry: false,
  });
  const invalidate = () =>
    void queryClient.invalidateQueries({
      queryKey: ["app-map-expectations", mapId],
    });
  const invalidateConflicts = () =>
    void queryClient.invalidateQueries({
      queryKey: ["app-map-conflicts", mapId],
    });
  const invalidateSuggestions = () =>
    void queryClient.invalidateQueries({
      queryKey: ["app-map-suggestions", mapId],
    });
  const invalidateDecided = () => {
    invalidate();
    invalidateSuggestions();
  };
  const promote = useMutation({
    mutationFn: (id: string) =>
      request(`${base}/app-maps/${mapId}/expectations/${id}/promote`, {
        method: "POST",
        body: JSON.stringify({ decided_by: "owner" }),
      }),
    onSuccess: invalidateDecided,
  });
  const reject = useMutation({
    mutationFn: (id: string) =>
      request(`${base}/app-maps/${mapId}/expectations/${id}/reject`, {
        method: "POST",
        body: JSON.stringify({ decided_by: "owner", reason: "Rejected in review" }),
      }),
    onSuccess: invalidateDecided,
  });
  const resolve = useMutation({
    mutationFn: (input: { id: string; resolution: string }) =>
      request(`${base}/app-maps/${mapId}/conflicts/${input.id}/resolve`, {
        method: "POST",
        body: JSON.stringify({
          resolution: input.resolution,
          decided_by: "owner",
          owner_text: ownerText[input.id] ?? "",
        }),
      }),
    onSuccess: invalidateConflicts,
  });
  const grounding = useMutation({
    mutationFn: () =>
      request(`${base}/app-maps/${mapId}/grounding`, {
        method: "POST",
        body: JSON.stringify({ probe }),
      }),
    onSuccess: invalidate,
  });

  const expectationItems = expectations.data?.items ?? [];
  const suggestionItems = suggestions.data?.items ?? [];
  const openConflicts = (conflicts.data?.items ?? []).filter(
    (conflict) => conflict.status === "open",
  );
  const gate = expectations.data?.gate as
    | { expectation_gate?: { release_scope?: string } }
    | undefined;
  return (
    <div className="app-map-phase2">
      <h4 style={{ marginBottom: "4px" }}>Expectations</h4>
      {expectations.isError && <p role="alert">Could not load expectations. <Button onClick={() => void expectations.refetch()}>Retry expectations</Button></p>}
      {suggestions.isError && <p role="alert">Could not load suggestions. <Button onClick={() => void suggestions.refetch()}>Retry suggestions</Button></p>}
      {conflicts.isError && <p role="alert">Could not load conflicts. <Button onClick={() => void conflicts.refetch()}>Retry conflicts</Button></p>}
      {audit.isError && (audit.error as { status?: number } | null)?.status !== 404 &&
        <p role="alert">Could not load the latest audit.</p>}
      {expectations.isPending ? (
        <p className="muted">Loading expectations…</p>
      ) : expectations.isError && !expectations.data ? null : expectationItems.length ? (
        <>
          <p className="muted" style={{ fontSize: "12px" }}>
            {expectationItems.length} expectations · gate scope:{" "}
            {gate?.expectation_gate?.release_scope ?? "none"}
          </p>
          <ul className="app-map-expectations">
            {expectationItems.slice(0, 10).map((item) => (
              <li key={item.id}>
                <span>{item.statement}</span>{" "}
                <StatusPill
                  tone={item.verdict_eligible ? "success" : "neutral"}
                  size="sm"
                >
                  {item.oracle_source} · {item.status}
                </StatusPill>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="muted">
          No expectations yet — run grounding to author them from the approved
          knowledge and the observed app.
        </p>
      )}
      <div style={{ display: "flex", gap: "8px", alignItems: "center", marginTop: "8px" }}>
        <Button
          variant="secondary"
          onClick={() => grounding.mutate()}
          disabled={grounding.isPending}
        >
          Ground expectations
        </Button>
        <label style={{ fontSize: "12px" }}>
          <input
            type="checkbox"
            checked={probe}
            onChange={(event) => setProbe(event.target.checked)}
          />{" "}
          Probe form validation
        </label>
      </div>
      <p className="muted" style={{ fontSize: "12px" }}>
        Probing runs only when approved test data accompanies the grounding
        request; without it the probe step is skipped and named in the
        grounding metrics.
      </p>
      {suggestionItems.length ? (
        <>
          <h4 style={{ marginBottom: "4px" }}>Suggestions</h4>
          <ul className="app-map-suggestions">
            {suggestionItems.map((item) => (
              <li key={item.id}>
                <span>{item.statement}</span>{" "}
                <StatusPill tone="warning" size="sm">
                  {item.oracle_source} · unverified
                </StatusPill>{" "}
                <Button
                  variant="secondary"
                  onClick={() => promote.mutate(item.id)}
                  disabled={promote.isPending}
                >
                  Approve
                </Button>{" "}
                <Button
                  variant="secondary"
                  onClick={() => reject.mutate(item.id)}
                  disabled={reject.isPending}
                >
                  Reject
                </Button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {openConflicts.length ? (
        <>
          <h4 style={{ marginBottom: "4px" }}>Conflicts</h4>
          <ul className="app-map-conflicts">
            {openConflicts.map((conflict) => (
              <li key={conflict.id}>
                <span>{conflict.observed_behaviour}</span>{" "}
                <StatusPill tone="warning" size="sm">
                  {conflict.conflict_kind ?? "conflict"} ·{" "}
                  {conflict.detection_source ?? "grounding"}
                </StatusPill>{" "}
                <Button
                  variant="secondary"
                  onClick={() =>
                    resolve.mutate({ id: conflict.id, resolution: "docs-win" })
                  }
                  disabled={resolve.isPending}
                >
                  Docs win
                </Button>{" "}
                <input
                  aria-label="Your corrected statement"
                  placeholder="Your corrected statement"
                  value={ownerText[conflict.id] ?? ""}
                  onChange={(event) =>
                    setOwnerText((current) => ({
                      ...current,
                      [conflict.id]: event.target.value,
                    }))
                  }
                />{" "}
                <Button
                  variant="secondary"
                  onClick={() =>
                    resolve.mutate({ id: conflict.id, resolution: "app-win" })
                  }
                  disabled={resolve.isPending}
                >
                  App wins
                </Button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {audit.data && Array.isArray(audit.data.findings) ? (
        <p className="muted" style={{ fontSize: "12px" }}>
          Latest audit: {audit.data.audit_kind} ·{" "}
          {audit.data.findings.length} findings
          {audit.data.created_at
            ? ` · ${new Date(audit.data.created_at).toLocaleString()}`
            : ""}
        </p>
      ) : null}
    </div>
  );
}

// The skill lifecycle words live in lib/status.ts (the "skill"
// source); this section only groups and renders them. The four groups
// and their order are doc 29 section 8.2; retired versions collapse
// into a sub-list under the same section.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "../../lib/api";
import { StatusPill } from "../ui/StatusBadge";
import { Button } from "../ui/button";
import { AppMapExpectations } from "./AppMapExpectations";
import { AppMapFreshness } from "./AppMapFreshness";
import { AppMapSkills } from "./AppMapSkills";

/**
 * The application map panel (doc 16 section 10.4): the observed map
 * of one application target — census counts, harvest coverage,
 * enrichment spend, and the verified skill line — with the Build and
 * Harvest actions. The map is built from the live site, in code;
 * model calls happen only inside harvest enrichment, under the caps
 * recorded on the map itself.
 */

export interface AppMapHarvestBlock {
  status: string;
  visited: number;
  reachable: number;
  blocked: number;
  failed: number;
  unprobed_budget: number;
  enriched_groups: number;
  template_groups: number;
  spend: { calls: number; tokens: number };
}

export interface AppMapSkillLine {
  name: string;
  lifecycle_status: string | null;
  last_replay_result: string | null;
  last_replay_at: string | null;
}

export interface AppMapExpectationLine {
  id: string;
  statement: string;
  oracle_source: string;
  status: string;
  verdict_eligible: boolean;
  assertion_kind: string | null;
}

export interface AppMapConflictLine {
  id: string;
  expectation_id: string;
  conflict_kind: string | null;
  detection_source: string | null;
  observed_behaviour: string;
  status: string;
}

export interface AppMapAuditLine {
  audit_kind: string;
  checks: Record<string, unknown>;
  findings: unknown[];
  created_at: string | null;
}

export interface AppMapFreshnessBlock {
  state: string;
  last_preflight_at: string | null;
  last_preflight_id: string | null;
  outcome_counts: Record<string, number>;
  deferred_count: number;
}

export interface AppMapSummary {
  research_queued?: boolean;
  map_id: string;
  version_number: number;
  status: string;
  release_state: string | null;
  release_scope: string | null;
  base_url: string;
  builder_version: string;
  started_at: string;
  completed_at: string | null;
  counts: { expected: number; reachable: number; by_status: Record<string, number> };
  gate_metrics: Record<string, unknown>;
  spend: { calls: number; tokens: number; seconds: number };
  harvest: AppMapHarvestBlock;
  freshness: AppMapFreshnessBlock;
  skills: AppMapSkillLine[];
}

const STALE_AFTER_MS = 7 * 24 * 3600 * 1000;

function stalenessLabel(summary: AppMapSummary): string {
  const built = summary.completed_at ?? summary.started_at;
  const age = Date.now() - new Date(built).getTime();
  return age <= STALE_AFTER_MS ? "current" : "stale";
}

export function AppMapPanel({
  workspaceId,
  applicationId,
  targetId,
}: {
  workspaceId: string;
  applicationId: string;
  targetId: string;
}) {
  const queryClient = useQueryClient();
  const base =
    `/api/v1/workspaces/${workspaceId}/applications/${applicationId}` +
    `/targets/${targetId}`;
  const summary = useQuery({
    queryKey: ["app-map", workspaceId, applicationId, targetId],
    queryFn: () => request<AppMapSummary>(`${base}/app-map`),
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && (data.status === "building" || data.harvest.status === "building" || data.research_queued)
        ? 5000
        : false;
    },
  });

  const invalidate = () =>
    void queryClient.invalidateQueries({
      queryKey: ["app-map", workspaceId, applicationId, targetId],
    });
  const build = useMutation({
    mutationFn: () => request(`${base}/map-builds`, { method: "POST" }),
    onSuccess: invalidate,
  });
  const mapId = summary.data?.map_id;
  const harvest = useMutation({
    mutationFn: () =>
      request(`${base}/app-maps/${mapId}/harvest`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    onSuccess: invalidate,
  });
  const preflight = useMutation({
    mutationFn: () =>
      request(`${base}/app-maps/${mapId}/preflights`, { method: "POST" }),
    onSuccess: invalidate,
  });

  if (summary.isPending) {
    return (
      <section className="panel app-map-panel" aria-label="Application map">
        <p className="muted">Loading the application map…</p>
      </section>
    );
  }

  if (summary.isError && !summary.data &&
      (summary.error as { status?: number } | null)?.status !== 404) {
    return (
      <section className="panel app-map-panel" aria-label="Application map">
        <p role="alert">Could not load the application map.</p>
        <Button onClick={() => void summary.refetch()}>Try again</Button>
      </section>
    );
  }

  if (!summary.data) {
    return (
      <section className="panel app-map-panel" aria-label="Application map">
        <p>
          No application map yet — the map is built from the live site, in code,
          with no model calls
        </p>
        <Button onClick={() => build.mutate()} disabled={build.isPending}>
          {build.isPending ? "Starting…" : "Build app map"}
        </Button>
        {build.isError ? <p role="alert">Could not start knowledge ingestion. Try again.</p> : null}
      </section>
    );
  }

  const data = summary.data;
  const built = data.completed_at ?? data.started_at;
  return (
    <section className="panel app-map-panel" aria-label="Application map">
      {summary.isError && (
        <p role="alert">Could not refresh the application map. Showing the last loaded data.</p>
      )}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        <h3 id="app-map-version" style={{ margin: 0 }}>Map v{data.version_number}</h3>
        <StatusPill tone={data.release_state === "partial" ? "warning" : "neutral"} size="sm">
          {data.release_state ?? "unreleased"}
          {data.release_scope ? ` · ${data.release_scope} scope` : ""}
        </StatusPill>
        <Button
          onClick={() => build.mutate()}
          disabled={build.isPending || data.status === "building"}
        >
          {build.isPending ? "Starting…" : data.status === "building" ? "Building app map…" : "Build app map"}
        </Button>
      </div>
      {build.isError ? <p role="alert">Could not start knowledge ingestion. Try again.</p> : null}
      {build.isSuccess ? <p role="status">Knowledge build requested for this application.</p> : null}
      {data.status === "building" ? <p role="status">Knowledge ingestion is running. {data.counts.expected} pages discovered so far.</p> : null}
      {data.status === "failed" ? <p role="alert">Knowledge ingestion failed. Try again to start another build.</p> : null}
      <p className="muted" style={{ fontSize: "12px" }}>
        Built {new Date(built).toLocaleString()} · {stalenessLabel(data)} ·{" "}
        {data.base_url}
      </p>
      <nav className="app-map-anchor-nav" aria-label="Application knowledge sections">
        <a href="#app-map-version">Map</a>{" · "}
        <a href="#app-map-freshness">Freshness</a>
        {mapId ? <>{" · "}<a href="#app-map-skills">Skills</a>{" · "}
          <a href="#app-map-expectations">Expectations</a></> : null}
      </nav>
      <dl className="app-map-counts">
        <div>
          <dt>Pages</dt>
          <dd>
            {data.counts.reachable} reachable of {data.counts.expected} expected
          </dd>
        </div>
        <div>
          <dt>Harvest</dt>
          <dd>
            {data.harvest.status === "not_started"
              ? data.research_queued ? "Workflow research queued" : "Not harvested yet"
              : `${data.harvest.visited} visited of ${data.harvest.reachable} reachable` +
                ` · ${data.harvest.blocked} blocked` +
                ` · ${data.harvest.failed} failed` +
                ` · ${data.harvest.unprobed_budget} unprobed (budget)`}
          </dd>
        </div>
        <AppMapFreshness freshness={data.freshness} />
        <div>
          <dt>Enrichment</dt>
          <dd>
            {data.harvest.enriched_groups} of {data.harvest.template_groups}{" "}
            template groups enriched · {data.harvest.spend.calls} model calls ·{" "}
            {data.harvest.spend.tokens} tokens
          </dd>
        </div>
      </dl>
      {/* Skills render once, grouped, in the Skill library section below. */}
      {mapId ? <div id="app-map-skills"><AppMapSkills base={base} /></div> : null}
      {mapId ? <div id="app-map-expectations"><AppMapExpectations base={base} mapId={mapId} /></div> : null}
      <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
        <Button
          onClick={() => harvest.mutate()}
          disabled={
            harvest.isPending ||
            data.status !== "ready" ||
            data.harvest.status === "building"
          }
        >
          Harvest
        </Button>
        <Button
          variant="secondary"
          onClick={() => preflight.mutate()}
          disabled={
            preflight.isPending ||
            data.status !== "ready" ||
            data.harvest.status === "building"
          }
        >
          Check freshness
        </Button>
      </div>
      {harvest.isError ? <p role="alert">Could not start the harvest. Try again.</p> : null}
      {preflight.isError ? <p role="alert">Could not check freshness. Try again.</p> : null}
    </section>
  );
}

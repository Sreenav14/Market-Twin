import { useQuery } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";
import { ArrowUpRight, Compass, ShieldCheck, FileCheck2 } from "lucide-react";
import { RunContext } from "../../layouts/RunLayout";
import { api, request } from "../../lib/api";
import { terminalTestStatuses } from "../../lib/results";
import { journeyBlocker, journeyIdentity } from "../../lib/journeyPresentation";
import { groupJourneys } from "../../lib/testerWork";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { FeatureCases } from "../../components/markettwin/FeatureCases";

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function RunJourneysPage() {
  const { run, user } = useOutletContext<RunContext>();
  const isDeep = run.configuration_snapshot.execution_mode === "deep_feature_v1";

  const journeys = useQuery({
    queryKey: ["run-journeys", user.id, run.id],
    queryFn: ({ signal }) => api.getRunJourneys(run.id, signal),
    refetchInterval: terminalTestStatuses.has(run.status) ? false : 5_000,
  });

  const collection = useQuery({
    queryKey: ["run-collection", user.id, run.id],
    queryFn: ({ signal }) =>
      request<{ collection: Record<string, unknown> | null; collected_at: string | null }>(
        `/api/v1/test-runs/${run.id}/collection`,
        { signal },
      ),
    refetchInterval: terminalTestStatuses.has(run.status) ? false : 5_000,
  });

  const allJourneys = journeys.data || [];

  // In deep_feature_v1 mode: partition into Discovery Stage and Planned Feature Cases
  const discoveryJourneys = isDeep
    ? allJourneys.filter((j) => journeyIdentity(j, isDeep).discovery)
    : [];
  const plannedCaseJourneys = isDeep
    ? allJourneys.filter((j) => !journeyIdentity(j, isDeep).discovery)
    : [];

  // In persona journeys mode: group by testing goal / mission first
  const missionGroups = !isDeep
    ? groupJourneys(allJourneys, (journey) => journey.mission_title)
    : [];

  return (
    <section aria-labelledby="execution-results-heading">
      {isDeep ? <FeatureCases runId={run.id} userId={user.id} /> : null}

      <div className="section-heading" style={{ marginBottom: 20 }}>
        <div>
          <h2 id="execution-results-heading">
            {isDeep ? "Browser execution records" : "Journeys by testing goal"}
          </h2>
          <p className="muted">
            {isDeep
              ? "Discovery inspects the authorized target before planning. Planned feature cases execute separately; open a case record to inspect its recorded steps and evidence."
              : "Grouped by planned testing goal. Each simulated tester attempts the goal independently; execution phase and product outcome are recorded separately."}
          </p>
        </div>
        <Link to={`/runs/${run.id}/evaluation`} className="text-link" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <span>View evaluation</span>
          <ArrowUpRight size={14} aria-hidden="true" />
        </Link>
      </div>

      {collection.data?.collection ? (
        <p className="inline-note" style={{ marginBottom: 24 }}>
          {isDeep ? "Case collector recorded" : "Supervisor collected"}{" "}
          <strong>{String(collection.data.collection.journey_count ?? collection.data.collection.executed)}</strong>{" "}
          {isDeep ? "case" : "journey"} outputs
          {collection.data.collected_at ? ` · ${new Date(collection.data.collected_at).toLocaleString()}` : ""}.
          {" "}Evaluation uses these saved outputs and their visual evidence.
        </p>
      ) : collection.isError ? (
        <p className="error-text" role="alert" style={{ marginBottom: 20 }}>
          Could not load recorded collection: {collection.error.message}
        </p>
      ) : null}

      {journeys.isPending ? (
        <LoadingPanel label="Loading journey results" />
      ) : journeys.isError ? (
        <ErrorPanel
          message={journeys.error.message}
          action={<Button variant="secondary" onClick={() => void journeys.refetch()}>Try again</Button>}
        />
      ) : !allJourneys.length ? (
        <EmptyState
          title="No journeys planned yet"
          copy={
            run.status === "draft"
              ? "Start this test to generate its plan and browser assignments."
              : "Journeys appear once the planner saves its assignments."
          }
        />
      ) : isDeep ? (
        /* Deep Feature Mode: Separate Discovery Stage from Planned Cases */
        <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
          {/* 01 / Target Discovery Stage */}
          {discoveryJourneys.length > 0 ? (
            <section aria-labelledby="discovery-stage-heading">
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  marginBottom: 14,
                  paddingBottom: 8,
                  borderBottom: "1px solid var(--border)",
                }}
              >
                <Compass size={18} style={{ color: "var(--primary)" }} aria-hidden="true" />
                <h3 id="discovery-stage-heading" style={{ fontSize: 16, margin: 0, fontWeight: 650 }}>
                  01 / Target Discovery Stage
                </h3>
                <span
                  style={{
                    fontSize: 11,
                    fontFamily: "var(--font-mono, monospace)",
                    color: "var(--text-3)",
                    marginLeft: "auto",
                  }}
                >
                  PRE-PLANNING
                </span>
              </div>
              <p style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 16 }}>
                Inspects the authorized target origin to map accessible pages and interactive controls prior to generating deterministic test cases.
              </p>

              <div className="run-records">
                {discoveryJourneys.map((journey) => (
                  <article className="panel run-record" id={`journey-${journey.id}`} key={journey.id}>
                    <div className="section-heading" style={{ alignItems: "flex-start", gap: 16 }}>
                      <div>
                        <h4 style={{ margin: "0 0 6px", fontSize: 16 }}>
                          <Link to={`/runs/${run.id}/journeys/${journey.id}`}>
                            Browser Discovery & Scope Verification
                          </Link>
                        </h4>
                        <p className="muted" style={{ margin: 0 }}>
                          Executor: Browser discovery · {journey.step_count} recorded steps · {journey.artifact_count} artifacts
                        </p>
                      </div>
                      <div className="run-record-badges">
                        <span>Execution <StatusBadge status={journey.execution_status || "not started"} /></span>
                      </div>
                    </div>

                    {typeof journey.result?.summary === "string" ? <p>{journey.result.summary}</p> : null}
                    {journey.error_message ? <p className="error-text">{journey.error_message}</p> : null}
                    {journeyBlocker(journey) ? <p className="inline-note">{journeyBlocker(journey)}</p> : null}

                    <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 14 }}>
                      <Link
                        className="primary-button compact"
                        to={`/runs/${run.id}/journeys/${journey.id}`}
                      >
                        Inspect recorded steps and evidence
                        <ArrowUpRight size={13} aria-hidden="true" />
                      </Link>
                      <Link className="text-link" to={`/runs/${run.id}/human-action`}>
                        Human Assistance history
                      </Link>
                    </div>

                    <details style={{ marginTop: 14 }}>
                      <summary>Discovery checks & recorded observations</summary>
                      <h4>Discovery checks</h4>
                      <p>Inspect the authorized page before generating test cases. Authentication assistance is requested only when encountered.</p>
                      {(["report_validation_issues", "actions", "observations", "friction_points", "blockers"] as const).map((field) => {
                        const items = strings(journey.result?.[field]);
                        return items.length ? (
                          <div key={field}>
                            <h4>{field === "report_validation_issues" ? "Report checks" : field.replaceAll("_", " ")}</h4>
                            <ul>
                              {items.map((item, index) => (
                                <li key={index}>{item}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null;
                      })}
                    </details>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          {/* 02 / Planned Feature Cases */}
          <section aria-labelledby="planned-cases-heading">
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                marginBottom: 14,
                paddingBottom: 8,
                borderBottom: "1px solid var(--border)",
              }}
            >
              <FileCheck2 size={18} style={{ color: "var(--primary)" }} aria-hidden="true" />
              <h3 id="planned-cases-heading" style={{ fontSize: 16, margin: 0, fontWeight: 650 }}>
                02 / Planned Feature Cases
              </h3>
              <span
                style={{
                  fontSize: 11,
                  fontFamily: "var(--font-mono, monospace)",
                  color: "var(--text-3)",
                  marginLeft: "auto",
                }}
              >
                {plannedCaseJourneys.length} CASE{plannedCaseJourneys.length === 1 ? "" : "S"}
              </span>
            </div>

            <div className="run-records">
              {plannedCaseJourneys.map((journey) => {
                const identity = journeyIdentity(journey, isDeep);
                return (
                  <article className="panel run-record" id={`journey-${journey.id}`} key={journey.id}>
                    <div className="section-heading" style={{ alignItems: "flex-start", gap: 16 }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
                          {identity.caseId ? (
                            <span
                              style={{
                                fontSize: 11,
                                padding: "2px 8px",
                                borderRadius: 4,
                                background: "var(--surface-muted)",
                                border: "1px solid var(--border)",
                                fontFamily: "var(--font-mono, monospace)",
                                fontWeight: 600,
                              }}
                            >
                              Case {identity.caseId}
                            </span>
                          ) : null}
                          <h4 style={{ margin: 0, fontSize: 16 }}>
                            <Link to={`/runs/${run.id}/journeys/${journey.id}`}>
                              {journey.mission_title}
                            </Link>
                          </h4>
                        </div>
                        <p className="muted" style={{ margin: 0 }}>
                          Executor: {identity.executor}
                          {journey.attempt_number ? ` · Attempt ${journey.attempt_number}` : ""} · {journey.step_count} steps · {journey.artifact_count} artifacts
                        </p>
                      </div>

                      <div className="run-record-badges">
                        <span>Execution <StatusBadge status={journey.execution_status || "not started"} /></span>
                        <span>Outcome <StatusBadge status={journey.outcome || "not recorded"} /></span>
                      </div>
                    </div>

                    {typeof journey.result?.summary === "string" ? <p>{journey.result.summary}</p> : null}
                    {journey.error_message ? <p className="error-text">{journey.error_message}</p> : null}
                    {journeyBlocker(journey) ? <p className="inline-note">{journeyBlocker(journey)}</p> : null}

                    <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 14 }}>
                      <Link
                        className="primary-button compact"
                        to={`/runs/${run.id}/journeys/${journey.id}`}
                      >
                        Inspect recorded steps and evidence
                        <ArrowUpRight size={13} aria-hidden="true" />
                      </Link>
                      <Link className="text-link" to={`/runs/${run.id}/human-action`}>
                        Human Assistance history
                      </Link>
                    </div>

                    <details style={{ marginTop: 14 }}>
                      <summary>Criteria and recorded observations</summary>
                      <h4>Success criteria</h4>
                      <ul>
                        {journey.success_criteria.map((criterion, index) => (
                          <li key={index}>{criterion}</li>
                        ))}
                      </ul>
                      {(["report_validation_issues", "actions", "observations", "friction_points", "blockers"] as const).map((field) => {
                        const items = strings(journey.result?.[field]);
                        return items.length ? (
                          <div key={field}>
                            <h4>{field === "report_validation_issues" ? "Report checks" : field.replaceAll("_", " ")}</h4>
                            <ul>
                              {items.map((item, index) => (
                                <li key={index}>{item}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null;
                      })}
                    </details>
                  </article>
                );
              })}
            </div>
          </section>
        </div>
      ) : (
        /* Persona Journeys Mode: Group by Testing Goal / Mission First */
        <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
          {missionGroups.map((group) => {
            const firstJourney = group.journeys[0];
            return (
              <section
                key={group.key}
                aria-labelledby={`goal-${group.key.toLowerCase().replaceAll(/\s+/g, "-")}`}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: 10,
                  background: "var(--surface)",
                  padding: 24,
                }}
              >
                {/* Goal Header */}
                <div style={{ marginBottom: 18, paddingBottom: 16, borderBottom: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <ShieldCheck size={18} style={{ color: "var(--primary)" }} aria-hidden="true" />
                      <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-3)" }}>
                        Testing Goal
                      </span>
                    </div>
                    <span style={{ fontSize: 12, color: "var(--text-3)", fontWeight: 500 }}>
                      {group.journeys.length} simulated tester attempt{group.journeys.length === 1 ? "" : "s"}
                    </span>
                  </div>

                  <h3
                    id={`goal-${group.key.toLowerCase().replaceAll(/\s+/g, "-")}`}
                    style={{ fontSize: 20, margin: "8px 0 6px", fontWeight: 650 }}
                  >
                    {group.key}
                  </h3>

                  {firstJourney.mission_objective ? (
                    <p style={{ margin: 0, color: "var(--text-2)", fontSize: 14 }}>
                      {firstJourney.mission_objective}
                    </p>
                  ) : null}

                  {firstJourney.success_criteria.length > 0 ? (
                    <details style={{ marginTop: 12 }}>
                      <summary style={{ fontSize: 13, color: "var(--text-3)" }}>
                        Planned success criteria ({firstJourney.success_criteria.length})
                      </summary>
                      <ul style={{ margin: "8px 0 0", paddingLeft: 20, fontSize: 13 }}>
                        {firstJourney.success_criteria.map((criterion, idx) => (
                          <li key={idx} style={{ margin: "4px 0" }}>{criterion}</li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </div>

                {/* Tester Attempts for this Goal */}
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {group.journeys.map((journey) => (
                    <article
                      key={journey.id}
                      id={`journey-${journey.id}`}
                      style={{
                        padding: 18,
                        borderRadius: 8,
                        background: "var(--surface-muted)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          justifyContent: "space-between",
                          gap: 16,
                          flexWrap: "wrap",
                        }}
                      >
                        <div>
                          <h4 style={{ margin: "0 0 4px", fontSize: 16, fontWeight: 600 }}>
                            <Link to={`/runs/${run.id}/journeys/${journey.id}`}>
                              {journey.persona_name}
                            </Link>
                          </h4>
                          <p style={{ margin: "0 0 6px", fontSize: 13, color: "var(--text-2)" }}>
                            {journey.persona_perspective}
                          </p>
                          <p className="muted" style={{ margin: 0, fontSize: 12 }}>
                            Journey {journey.ordinal}
                            {journey.attempt_number ? ` · Attempt ${journey.attempt_number}` : ""} · {journey.step_count} steps · {journey.artifact_count} artifacts
                          </p>
                        </div>

                        <div className="run-record-badges">
                          <span>Execution <StatusBadge status={journey.execution_status || "not started"} /></span>
                          <span>Outcome <StatusBadge status={journey.outcome || "not recorded"} /></span>
                        </div>
                      </div>

                      {typeof journey.result?.summary === "string" ? (
                        <p style={{ marginTop: 12, fontSize: 14 }}>{journey.result.summary}</p>
                      ) : null}
                      {journey.error_message ? <p className="error-text">{journey.error_message}</p> : null}
                      {journeyBlocker(journey) ? <p className="inline-note">{journeyBlocker(journey)}</p> : null}

                      <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 14 }}>
                        <Link
                          className="primary-button compact"
                          to={`/runs/${run.id}/journeys/${journey.id}`}
                        >
                          Inspect recorded steps and evidence
                          <ArrowUpRight size={13} aria-hidden="true" />
                        </Link>
                        <Link className="text-link" to={`/runs/${run.id}/human-action`}>
                          Human Assistance history
                        </Link>
                      </div>

                      <details style={{ marginTop: 14 }}>
                        <summary>Criteria and recorded observations</summary>
                        <h4>Success criteria</h4>
                        <ul>
                          {journey.success_criteria.map((criterion, index) => (
                            <li key={index}>{criterion}</li>
                          ))}
                        </ul>
                        {(["report_validation_issues", "actions", "observations", "friction_points", "blockers"] as const).map((field) => {
                          const items = strings(journey.result?.[field]);
                          return items.length ? (
                            <div key={field}>
                              <h4>{field === "report_validation_issues" ? "Report checks" : field.replaceAll("_", " ")}</h4>
                              <ul>
                                {items.map((item, index) => (
                                  <li key={index}>{item}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null;
                        })}
                      </details>
                    </article>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </section>
  );
}

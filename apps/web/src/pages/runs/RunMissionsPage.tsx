import { useQuery } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";
import { Target, ArrowUpRight, ListChecks } from "lucide-react";
import { RunContext } from "../../layouts/RunLayout";
import { api } from "../../lib/api";
import { terminalTestStatuses } from "../../lib/results";
import { groupJourneys, simulatedTesterJourneys } from "../../lib/testerWork";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { StatusBadge } from "../../components/ui/StatusBadge";

export function RunMissionsPage() {
  const { run, user } = useOutletContext<RunContext>();
  const isDeep = run.configuration_snapshot.execution_mode === "deep_feature_v1";

  const journeys = useQuery({
    queryKey: ["run-journeys", user.id, run.id],
    queryFn: ({ signal }) => api.getRunJourneys(run.id, signal),
    refetchInterval: terminalTestStatuses.has(run.status) ? false : 5_000,
  });

  const missions = journeys.data
    ? groupJourneys(simulatedTesterJourneys(journeys.data, isDeep), (journey) => journey.mission_title)
    : [];

  return (
    <section aria-labelledby="testing-goals-heading">
      <div className="section-heading" style={{ marginBottom: 20 }}>
        <div>
          <h2 id="testing-goals-heading">Testing goals</h2>
          <p className="muted">
            Compact coverage matrix of planned testing goals and criteria against attempted persona outcomes.
          </p>
        </div>
      </div>

      {isDeep ? (
        <EmptyState
          title="Feature cases do not use persona goals"
          copy="Each Feature Case is an explicit planned check listed under Journeys, with deterministic browser steps and assertions."
          action={
            <Link className="secondary-button" to={`/runs/${run.id}/journeys`}>
              View Feature Cases
            </Link>
          }
        />
      ) : journeys.isPending ? (
        <LoadingPanel label="Loading testing goals" />
      ) : journeys.isError ? (
        <ErrorPanel
          message={journeys.error.message}
          action={<Button variant="secondary" onClick={() => void journeys.refetch()}>Try again</Button>}
        />
      ) : !missions.length ? (
        <EmptyState
          title="No testing goals planned yet"
          copy={
            run.status === "draft"
              ? "Start this test to generate its plan and assign testing goals."
              : "Testing goals appear once the planner saves its assignments."
          }
        />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
          {missions.map((group) => {
            const first = group.journeys[0];
            return (
              <article
                className="panel run-record"
                key={group.key}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: 10,
                  background: "var(--surface)",
                  padding: 24,
                }}
              >
                {/* Mission Header */}
                <div style={{ paddingBottom: 16, borderBottom: "1px solid var(--border)", marginBottom: 18 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Target size={18} style={{ color: "var(--primary)" }} aria-hidden="true" />
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          textTransform: "uppercase",
                          letterSpacing: "0.08em",
                          color: "var(--text-3)",
                        }}
                      >
                        Testing Goal
                      </span>
                    </div>
                    <span style={{ fontSize: 12, color: "var(--text-3)" }}>
                      {group.journeys.length} attempted perspective{group.journeys.length === 1 ? "" : "s"}
                    </span>
                  </div>

                  <h3 style={{ margin: "6px 0 6px", fontSize: 20, fontWeight: 650 }}>
                    {first.mission_title}
                  </h3>
                  <p style={{ margin: 0, fontSize: 14, color: "var(--text-2)", lineHeight: 1.5 }}>
                    {first.mission_objective}
                  </p>
                  <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--text-3)" }}>
                    <span style={{ fontWeight: 600, color: "var(--text-2)" }}>Simulated testers: </span>
                    <span>{[...new Set(group.journeys.map((j) => j.persona_name))].join(", ")}</span>
                  </p>

                  {/* Planned Criteria */}
                  {first.success_criteria.length > 0 ? (
                    <div style={{ marginTop: 14, padding: "12px 16px", borderRadius: 6, background: "var(--surface-muted)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                        <ListChecks size={14} style={{ color: "var(--primary)" }} aria-hidden="true" />
                        <strong style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-3)" }}>
                          Planned Success Criteria ({first.success_criteria.length})
                        </strong>
                      </div>
                      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "var(--text)" }}>
                        {first.success_criteria.map((criterion, idx) => (
                          <li key={idx} style={{ margin: "4px 0" }}>{criterion}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>

                {/* Compact Coverage Matrix Table */}
                <div>
                  <h4 style={{ margin: "0 0 10px", fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-3)" }}>
                    Coverage Matrix: Tester Attempts & Outcomes
                  </h4>

                  <div
                    style={{
                      border: "1px solid var(--border)",
                      borderRadius: 6,
                      overflow: "hidden",
                    }}
                  >
                    {/* Matrix Table Heading */}
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "minmax(140px, 1.2fr) minmax(180px, 2fr) 130px 130px auto",
                        gap: 12,
                        padding: "10px 16px",
                        background: "var(--surface-muted)",
                        borderBottom: "1px solid var(--border)",
                        fontSize: 12,
                        fontWeight: 600,
                        color: "var(--text-3)",
                      }}
                    >
                      <span>Simulated Tester</span>
                      <span>Perspective Context</span>
                      <span>Execution</span>
                      <span>Outcome</span>
                      <span style={{ textAlign: "right" }}>Evidence</span>
                    </div>

                    {/* Matrix Table Rows */}
                    {group.journeys.map((journey, rowIdx) => (
                      <div
                        key={journey.id}
                        style={{
                          display: "grid",
                          gridTemplateColumns: "minmax(140px, 1.2fr) minmax(180px, 2fr) 130px 130px auto",
                          gap: 12,
                          alignItems: "center",
                          padding: "12px 16px",
                          borderTop: rowIdx === 0 ? "none" : "1px solid var(--border)",
                          background: rowIdx % 2 === 1 ? "rgba(0,0,0,0.01)" : "transparent",
                          fontSize: 13,
                        }}
                      >
                        <div>
                          <Link
                            to={`/runs/${run.id}/journeys/${journey.id}`}
                            style={{
                              fontWeight: 600,
                              color: "var(--text)",
                              textDecoration: "none",
                            }}
                          >
                            {journey.persona_name}
                          </Link>
                          <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 2 }}>
                            Journey {journey.ordinal}
                          </div>
                        </div>

                        <div style={{ color: "var(--text-2)", fontSize: 12, overflowWrap: "anywhere" }}>
                          {journey.persona_perspective}
                        </div>

                        <div>
                          <StatusBadge status={journey.execution_status || "not started"} />
                        </div>

                        <div>
                          <StatusBadge status={journey.outcome || "not recorded"} />
                        </div>

                        <div style={{ display: "flex", justifyContent: "flex-end" }}>
                          <Link
                            to={`/runs/${run.id}/journeys/${journey.id}`}
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 4,
                              fontSize: 12,
                              fontWeight: 600,
                              color: "var(--primary)",
                              textDecoration: "none",
                              padding: "4px 8px",
                              borderRadius: 4,
                              background: "var(--surface-muted)",
                            }}
                          >
                            <span>Inspect ({journey.step_count} steps)</span>
                            <ArrowUpRight size={12} aria-hidden="true" />
                          </Link>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

import { useQuery } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";
import { Users, ArrowUpRight } from "lucide-react";
import { RunContext } from "../../layouts/RunLayout";
import { api } from "../../lib/api";
import { terminalTestStatuses } from "../../lib/results";
import { countLabels, groupJourneys, simulatedTesterJourneys } from "../../lib/testerWork";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { StatusBadge } from "../../components/ui/StatusBadge";

export function RunPerspectivesPage() {
  const { run, user } = useOutletContext<RunContext>();
  const isDeep = run.configuration_snapshot.execution_mode === "deep_feature_v1";

  const journeys = useQuery({
    queryKey: ["run-journeys", user.id, run.id],
    queryFn: ({ signal }) => api.getRunJourneys(run.id, signal),
    refetchInterval: terminalTestStatuses.has(run.status) ? false : 5_000,
  });

  const testers = journeys.data
    ? groupJourneys(simulatedTesterJourneys(journeys.data, isDeep), (journey) => journey.persona_name)
    : [];

  return (
    <section aria-labelledby="simulated-testers-heading">
      <div className="section-heading" style={{ marginBottom: 20 }}>
        <div>
          <h2 id="simulated-testers-heading">Simulated testers</h2>
          <p className="muted">
            Hypothetical synthetic testing perspectives configured for this test. They evaluate specific flows and edge cases; they do not represent real human participants or survey opinion.
          </p>
        </div>
      </div>

      {isDeep ? (
        <EmptyState
          title="Feature Cases do not use simulated testers"
          copy="Feature Cases run planned deterministic checks with a browser executor rather than simulated personas. Open Journeys to inspect each case's steps and evidence."
          action={
            <Link className="secondary-button" to={`/runs/${run.id}/journeys`}>
              View Feature Cases
            </Link>
          }
        />
      ) : journeys.isPending ? (
        <LoadingPanel label="Loading simulated testers" />
      ) : journeys.isError ? (
        <ErrorPanel
          message={journeys.error.message}
          action={<Button variant="secondary" onClick={() => void journeys.refetch()}>Try again</Button>}
        />
      ) : !testers.length ? (
        <EmptyState
          title="No simulated testers planned yet"
          copy={
            run.status === "draft"
              ? "Start this test to generate its plan and assign tester perspectives."
              : "Testers appear once the planner saves its assignments."
          }
        />
      ) : (
        <div className="run-records" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {testers.map((group) => {
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
                {/* Tester Header */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    justifyContent: "space-between",
                    gap: 16,
                    flexWrap: "wrap",
                    paddingBottom: 16,
                    borderBottom: "1px solid var(--border)",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <Users size={18} style={{ color: "var(--primary)" }} aria-hidden="true" />
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          textTransform: "uppercase",
                          letterSpacing: "0.08em",
                          color: "var(--text-3)",
                        }}
                      >
                        Hypothetical Perspective
                      </span>
                    </div>
                    <h3 style={{ margin: "2px 0 6px", fontSize: 20, fontWeight: 650 }}>
                      {first.persona_name}
                    </h3>
                    <p style={{ margin: 0, fontSize: 14, color: "var(--text-2)", lineHeight: 1.5, maxWidth: "75ch" }}>
                      {first.persona_perspective}
                    </p>
                  </div>

                  <div
                    style={{
                      padding: "6px 12px",
                      borderRadius: 6,
                      background: "var(--surface-muted)",
                      border: "1px solid var(--border)",
                      fontSize: 12,
                      color: "var(--text-3)",
                      fontWeight: 500,
                    }}
                  >
                    {group.journeys.length} planned journey{group.journeys.length === 1 ? "" : "s"}
                  </div>
                </div>

                {/* Execution & Outcome Summary Metrics */}
                <dl
                  className="definition-list"
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                    gap: 16,
                    margin: "16px 0",
                    padding: "12px 16px",
                    borderRadius: 6,
                    background: "var(--surface-muted)",
                  }}
                >
                  <div>
                    <dt style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase" }}>
                      Execution Summary
                    </dt>
                    <dd style={{ margin: "4px 0 0", fontSize: 13, fontWeight: 500, color: "var(--text)" }}>
                      {countLabels(group.journeys.map((j) => j.execution_status))}
                    </dd>
                  </div>
                  <div>
                    <dt style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase" }}>
                      Recorded Outcomes
                    </dt>
                    <dd style={{ margin: "4px 0 0", fontSize: 13, fontWeight: 500, color: "var(--text)" }}>
                      {countLabels(group.journeys.map((j) => j.outcome))}
                    </dd>
                  </div>
                </dl>

                {/* Assigned Testing Goals with Direct Links */}
                <div>
                  <h4 style={{ margin: "0 0 10px", fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-3)" }}>
                    Assigned Testing Goals ({group.journeys.length})
                  </h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {group.journeys.map((journey) => (
                      <div
                        key={journey.id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: 14,
                          padding: "10px 14px",
                          borderRadius: 6,
                          background: "var(--surface-muted)",
                          border: "1px solid var(--border)",
                        }}
                      >
                        <div style={{ minWidth: 0 }}>
                          <Link
                            to={`/runs/${run.id}/journeys/${journey.id}`}
                            style={{
                              fontSize: 14,
                              fontWeight: 600,
                              color: "var(--text)",
                              textDecoration: "none",
                            }}
                          >
                            {journey.mission_title}
                          </Link>
                          <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
                            Journey {journey.ordinal} · {journey.step_count} recorded steps · {journey.artifact_count} artifacts
                          </div>
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
                          <StatusBadge status={journey.execution_status || "not started"} />
                          <StatusBadge status={journey.outcome || "not recorded"} />
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
                            }}
                            aria-label={`Inspect ${journey.mission_title}`}
                          >
                            <span>Inspect</span>
                            <ArrowUpRight size={13} aria-hidden="true" />
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

import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Info, Cpu } from "lucide-react";
import { request } from "../../lib/api";
import { RunContext } from "../../layouts/RunLayout";
import { ResultsBoundary } from "../../components/markettwin/ResultsBoundary";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { RunAssessmentView } from "../../components/markettwin/RunAssessmentView";

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function RunEvaluationPage() {
  const { run, results, user } = useOutletContext<RunContext>();

  const agents = useQuery({
    queryKey: ["evaluation-agents", user.id, run.id],
    queryFn: ({ signal }) =>
      request<{
        id: string;
        agent_role: string;
        model_name: string | null;
        created_at: string;
        effective_instruction: string | null;
      }[]>(`/api/v1/test-runs/${run.id}/evaluation-agents`, { signal }),
    enabled: results.status === "ready",
  });

  const payload = results.status === "ready" ? results.data.report.payload : {};
  const recorded = Array.isArray(payload.evaluation_records);
  const records = recorded ? (payload.evaluation_records as unknown[]).map(object) : [];

  const assessment =
    payload.assessment && typeof payload.assessment === "object" && !Array.isArray(payload.assessment)
      ? (payload.assessment as Record<string, unknown>)
      : null;
  const hasNarrativeAssessment = assessment?.status === "completed";

  return (
    <ResultsBoundary>
      <section aria-labelledby="evaluation-heading">
        <div className="section-heading" style={{ marginBottom: 20 }}>
          <div>
            <h2 id="evaluation-heading">Evaluation records</h2>
            <p className="muted">
              Verification results evaluated from recorded journey outputs, visual artifacts, and planned assertions.
            </p>
          </div>
          <Link
            className="text-link"
            to={`/runs/${run.id}/findings`}
            style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
          >
            <span>View findings</span>
            <ArrowUpRight size={14} aria-hidden="true" />
          </Link>
        </div>

        {/* Narrative Model Assessment or Graceful Fallback */}
        {hasNarrativeAssessment ? (
          <RunAssessmentView assessment={payload.assessment} runId={run.id} />
        ) : (
          <div
            className="panel run-record"
            style={{
              borderLeft: "4px solid var(--text-3)",
              background: "var(--surface)",
              padding: 20,
              borderRadius: 8,
              marginBottom: 28,
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
              <Info size={20} style={{ color: "var(--text-2)", flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
              <div>
                <h3 style={{ margin: "0 0 6px", fontSize: 16, fontWeight: 650 }}>
                  Narrative assessment unavailable
                </h3>
                <p style={{ margin: 0, fontSize: 14, color: "var(--text-2)", lineHeight: 1.5 }}>
                  {typeof assessment?.reason === "string"
                    ? assessment.reason
                    : "An overall model assessment was not recorded for this test run. The evaluation model was not configured or did not complete."}
                </p>
                <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--text-3)" }}>
                  All visual evidence criteria, deterministic assertions, and recorded steps below remain fully verified and inspectable.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Visual Evidence Verification Ledger */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <h3 className="evaluation-records-heading" style={{ margin: 0, fontSize: 18, fontWeight: 650 }}>
              Visual evidence checks ({records.length})
            </h3>
            <span style={{ fontSize: 12, color: "var(--text-3)" }}>
              Evaluated against captured screenshots & steps
            </span>
          </div>

          {!recorded ? (
            <p className="inline-note">
              Detailed visual checks were not recorded for this report version. Saved findings and recorded steps remain available.
            </p>
          ) : !records.length ? (
            <p className="inline-note">
              No visual criteria were selected for verification in this evaluation. This does not indicate that every criterion passed.
            </p>
          ) : (
            <div
              style={{
                border: "1px solid var(--border)",
                borderRadius: 8,
                background: "var(--surface)",
                overflow: "hidden",
              }}
            >
              {/* Table Header */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "minmax(0, 1.8fr) 130px minmax(0, 2fr) minmax(160px, 1.2fr)",
                  gap: 16,
                  padding: "12px 20px",
                  background: "var(--surface-muted)",
                  borderBottom: "1px solid var(--border)",
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--text-3)",
                }}
              >
                <span>Criterion</span>
                <span>Verification Result</span>
                <span>Rationale & Observations</span>
                <span>Linked Steps & Evidence</span>
              </div>

              {/* Table Rows */}
              {records.map((record, index) => {
                const evidence = object(record.evidence);
                const artifacts = Array.isArray(evidence.artifact_ids)
                  ? evidence.artifact_ids.filter((item): item is string => typeof item === "string")
                  : [];
                const steps = Array.isArray(evidence.step_ids)
                  ? evidence.step_ids.filter((item): item is number => typeof item === "number")
                  : [];

                const statusStr =
                  record.status === "satisfied"
                    ? "passed"
                    : record.status === "unsatisfied"
                    ? "failed"
                    : "unverified";

                return (
                  <div
                    key={index}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "minmax(0, 1.8fr) 130px minmax(0, 2fr) minmax(160px, 1.2fr)",
                      gap: 16,
                      alignItems: "start",
                      padding: "16px 20px",
                      borderTop: index === 0 ? "none" : "1px solid var(--border)",
                    }}
                  >
                    {/* 1. Criterion */}
                    <div>
                      <strong style={{ display: "block", fontSize: 14, fontWeight: 600, color: "var(--text)", lineHeight: 1.4 }}>
                        {typeof record.criterion === "string" ? record.criterion : "Visual check"}
                      </strong>
                      <span style={{ display: "block", fontSize: 12, color: "var(--text-3)", marginTop: 4 }}>
                        Persona reported: {typeof record.reported_status === "string" ? record.reported_status : "not recorded"}
                      </span>
                    </div>

                    {/* 2. Verification Result */}
                    <div>
                      <StatusBadge status={statusStr} />
                    </div>

                    {/* 3. Rationale & Observations */}
                    <div>
                      <p style={{ margin: 0, fontSize: 13, color: "var(--text-2)", lineHeight: 1.5 }}>
                        {typeof record.rationale === "string" ? record.rationale : "No rationale was recorded."}
                      </p>
                      {Array.isArray(record.observed_details) && record.observed_details.length > 0 ? (
                        <ul style={{ margin: "8px 0 0", paddingLeft: 16, fontSize: 12, color: "var(--text-3)" }}>
                          {record.observed_details
                            .filter((item): item is string => typeof item === "string")
                            .map((item, detailIndex) => (
                              <li key={detailIndex} style={{ margin: "2px 0" }}>{item}</li>
                            ))}
                        </ul>
                      ) : null}
                    </div>

                    {/* 4. Linked Steps & Evidence */}
                    <div>
                      {steps.length > 0 ? (
                        <div style={{ fontSize: 12, color: "var(--text-2)", marginBottom: 6 }}>
                          <strong>Steps:</strong> {steps.join(", ")}
                        </div>
                      ) : null}

                      {artifacts.length > 0 ? (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                          {artifacts.map((id) => (
                            <Link
                              key={id}
                              to={`/runs/${run.id}/evidence/${id}`}
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 4,
                                padding: "3px 8px",
                                borderRadius: 4,
                                background: "var(--surface-muted)",
                                border: "1px solid var(--border)",
                                fontSize: 11,
                                fontFamily: "var(--font-mono, monospace)",
                                textDecoration: "none",
                                color: "var(--text)",
                              }}
                            >
                              <span>{id.slice(0, 8)}</span>
                              <ArrowUpRight size={11} aria-hidden="true" />
                            </Link>
                          ))}
                        </div>
                      ) : (
                        <span style={{ fontSize: 12, color: "var(--text-3)" }}>No artifact linked</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Collapsed Technical Runtime Metadata & Evaluation Agents */}
        <details
          className="panel"
          style={{
            marginTop: 24,
            padding: "16px 20px",
            borderRadius: 8,
            border: "1px solid var(--border)",
            background: "var(--surface)",
          }}
        >
          <summary
            style={{
              cursor: "pointer",
              fontWeight: 600,
              fontSize: 14,
              color: "var(--text)",
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <Cpu size={16} style={{ color: "var(--text-3)" }} aria-hidden="true" />
            <span>Advanced runtime metadata & evaluation agents</span>
            {agents.data?.length ? (
              <span
                style={{
                  fontSize: 11,
                  padding: "1px 6px",
                  borderRadius: 999,
                  background: "var(--surface-muted)",
                  color: "var(--text-3)",
                }}
              >
                {agents.data.length}
              </span>
            ) : null}
          </summary>

          <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
            <p style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 16 }}>
              Evaluation is performed by bounded evaluation agents assessing recorded outputs against criteria schemas and visual artifacts.
            </p>

            {agents.data?.length ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {agents.data.map((agent) => (
                  <div
                    key={agent.id}
                    style={{
                      padding: 14,
                      borderRadius: 6,
                      background: "var(--surface-muted)",
                      border: "1px solid var(--border)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
                      <strong style={{ fontSize: 14 }}>
                        {agent.agent_role === "visual_verifier"
                          ? "Visual evidence verifier"
                          : "Testing goal evaluator"}
                      </strong>
                      <span style={{ fontSize: 12, color: "var(--text-3)" }}>
                        {agent.model_name || "Model not recorded"} · {new Date(agent.created_at).toLocaleString()}
                      </span>
                    </div>

                    <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--text-2)" }}>
                      {agent.agent_role === "visual_verifier"
                        ? "Verifies screenshots captured during test execution against specific assertions."
                        : "Assesses individual journeys and the overall testing goal from saved outputs."}
                    </p>

                    {agent.effective_instruction ? (
                      <details style={{ marginTop: 10 }}>
                        <summary style={{ fontSize: 12, color: "var(--text-3)", cursor: "pointer" }}>
                          Effective agent instructions
                        </summary>
                        <pre
                          style={{
                            marginTop: 8,
                            padding: 10,
                            borderRadius: 4,
                            background: "var(--page)",
                            border: "1px solid var(--border)",
                            fontSize: 11,
                            overflowX: "auto",
                            whiteSpace: "pre-wrap",
                          }}
                        >
                          {agent.effective_instruction}
                        </pre>
                      </details>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : agents.isError ? (
              <p className="error-text" role="alert">
                Could not load evaluation agents: {agents.error.message}
              </p>
            ) : (
              <p style={{ fontSize: 13, color: "var(--text-3)" }}>No evaluation agents recorded.</p>
            )}
          </div>
        </details>
      </section>
    </ResultsBoundary>
  );
}

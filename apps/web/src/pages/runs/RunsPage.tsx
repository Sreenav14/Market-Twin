import { DeleteAction } from "../../components/markettwin/DeleteAction";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { Search, X, ArrowUpRight, Play, Eye, AlertTriangle, FileText, CheckCircle2 } from "lucide-react";
import { PageHeader } from "../../components/ui/PageHeader";
import {
  EmptyState,
  ErrorPanel,
  LoadingPanel,
} from "../../components/ui/StateViews";
import { TestStatusBadge } from "../../components/ui/StatusBadge";
import { Button } from "../../components/ui/button";
import { testTitle, testBrief, textValue } from "../../lib/format";
import { canDeleteTest } from "../../lib/results";
import { useWorkspaceTests } from "../../lib/useWorkspaceTests";
import { canManageLifecycle, canWriteWorkspace } from "../../lib/permissions";
import { AppShellContext } from "../../layouts/AppShell";
import type { TestRunStatus } from "../../lib/api";

function getRunPhase(status: string): string {
  switch (status) {
    case "draft":
      return "Draft";
    case "planning":
      return "Planning";
    case "queued":
      return "Queued";
    case "running":
      return "Executing";
    case "awaiting_human":
      return "Assistance Required";
    case "completed":
      return "Completed";
    case "failed":
      return "Execution Failed";
    case "cancelled":
      return "Cancelled";
    case "timed_out":
      return "Timed Out";
    case "policy_blocked":
      return "Policy Blocked";
    default:
      return String(status).replaceAll("_", " ");
  }
}

interface PrimaryAction {
  label: "Watch" | "Assist" | "Review" | "Configure" | "Inspect";
  to: string;
  variant: "primary" | "attention" | "secondary";
  icon: typeof Play;
}

function getPrimaryAction(status: string, runId: string): PrimaryAction {
  if (status === "awaiting_human") {
    return {
      label: "Assist",
      to: `/runs/${runId}/human-action`,
      variant: "attention",
      icon: AlertTriangle,
    };
  }
  if (status === "running" || status === "planning" || status === "queued") {
    return {
      label: "Watch",
      to: `/runs/${runId}/activity`,
      variant: "primary",
      icon: Eye,
    };
  }
  if (status === "completed") {
    return {
      label: "Review",
      to: `/runs/${runId}/overview`,
      variant: "secondary",
      icon: FileText,
    };
  }
  if (status === "draft") {
    return {
      label: "Configure",
      to: `/runs/${runId}/overview`,
      variant: "secondary",
      icon: Play,
    };
  }
  return {
    label: "Inspect",
    to: `/runs/${runId}/overview`,
    variant: "secondary",
    icon: CheckCircle2,
  };
}

function matchesStatusFilter(runStatus: string, filterValue: string): boolean {
  if (!filterValue || filterValue === "all") return true;
  if (filterValue === "awaiting_human" || filterValue === "needs_assistance") {
    return runStatus === "awaiting_human";
  }
  if (filterValue === "in_progress" || filterValue === "active") {
    return ["running", "planning", "queued"].includes(runStatus);
  }
  if (filterValue === "completed") {
    return runStatus === "completed";
  }
  if (filterValue === "stopped" || filterValue === "failed") {
    return ["failed", "cancelled", "timed_out", "policy_blocked"].includes(runStatus);
  }
  if (filterValue === "draft") {
    return runStatus === "draft";
  }
  return runStatus === filterValue;
}

export function RunsPage() {
  const { workspace, user } = useOutletContext<AppShellContext>();
  const state = useWorkspaceTests(user.id, workspace.id);
  const [params, setParams] = useSearchParams();
  const search = params.get("q") || "";
  const status = params.get("status") || "all";

  const allRuns = state.data?.runs || [];

  const counts = {
    all: allRuns.length,
    awaiting_human: allRuns.filter((r) => r.status === "awaiting_human").length,
    in_progress: allRuns.filter((r) => ["running", "planning", "queued"].includes(r.status)).length,
    completed: allRuns.filter((r) => r.status === "completed").length,
    stopped: allRuns.filter((r) => ["failed", "cancelled", "timed_out", "policy_blocked"].includes(r.status)).length,
    draft: allRuns.filter((r) => r.status === "draft").length,
  };

  const statusTabs = [
    { id: "all", label: "All Tests", count: counts.all },
    ...(counts.awaiting_human > 0 || status === "awaiting_human"
      ? [{ id: "awaiting_human", label: "Needs Assistance", count: counts.awaiting_human, alert: counts.awaiting_human > 0 }]
      : []),
    { id: "in_progress", label: "In Progress", count: counts.in_progress },
    { id: "completed", label: "Completed", count: counts.completed },
    { id: "stopped", label: "Failed / Stopped", count: counts.stopped },
    { id: "draft", label: "Drafts", count: counts.draft },
  ];

  const filteredRuns = allRuns.filter(
    (run) =>
      matchesStatusFilter(run.status, status) &&
      `${testTitle(run)} ${testBrief(run.configuration_snapshot)} ${textValue(run.target_snapshot.name, "")}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );

  function filter(key: string, value: string) {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (!value || value === "all") next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true },
    );
  }

  function clearAllFilters() {
    setParams({}, { replace: true });
  }

  const hasActiveFilters = Boolean(search || (status && status !== "all"));

  return (
    <>
      <PageHeader
        title="Tests"
        description="Track tests, help paused runs, and review recorded results."
        action={
          canWriteWorkspace(workspace.role) ? (
            <Link className="primary-button" to="/applications">
              New test
            </Link>
          ) : undefined
        }
      />

      {state.isPending ? (
        <LoadingPanel label="Loading tests" />
      ) : !state.data ? (
        <ErrorPanel
          message={state.error?.message || "Could not load tests."}
          action={
            <Button variant="secondary" onClick={() => void state.refetch()}>
              Try again
            </Button>
          }
        />
      ) : (
        <>
          {state.isError ? (
            <p className="inline-note" role="alert">
              Could not refresh tests. Showing the last loaded data.{" "}
              <Button variant="ghost" size="sm" onClick={() => void state.refetch()}>
                Try again
              </Button>
            </p>
          ) : null}

          {/* Filter Bar with Tabs and Clearable Search */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 20 }}>
            {/* Status Filter Tabs */}
            <div
              role="tablist"
              aria-label="Filter tests by status"
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 6,
                paddingBottom: 2,
                borderBottom: "1px solid var(--border)",
              }}
            >
              {statusTabs.map((tab) => {
                const isSelected = (status === "all" && tab.id === "all") || status === tab.id;
                return (
                  <button
                    key={tab.id}
                    role="tab"
                    aria-selected={isSelected}
                    type="button"
                    onClick={() => filter("status", tab.id)}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 7,
                      padding: "6px 12px",
                      borderRadius: "6px",
                      border: isSelected ? "1px solid var(--primary)" : "1px solid transparent",
                      background: isSelected
                        ? "var(--surface-muted)"
                        : "transparent",
                      color: isSelected ? "var(--text)" : "var(--text-3)",
                      fontSize: 13,
                      fontWeight: isSelected ? 600 : 500,
                      cursor: "pointer",
                      transition: "all 120ms ease",
                    }}
                  >
                    <span>{tab.label}</span>
                    <span
                      style={{
                        fontSize: 11,
                        padding: "1px 6px",
                        borderRadius: 999,
                        background: tab.alert
                          ? "var(--warning-bg)"
                          : isSelected
                          ? "var(--surface)"
                          : "var(--surface-muted)",
                        color: tab.alert
                          ? "var(--warning)"
                          : isSelected
                          ? "var(--text)"
                          : "var(--text-3)",
                        border: tab.alert ? "1px solid var(--warning-border)" : "none",
                        fontWeight: 600,
                      }}
                    >
                      {tab.count}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Search Input & Reset Controls */}
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <div
                style={{
                  position: "relative",
                  flex: "1 1 280px",
                  maxWidth: 440,
                  display: "flex",
                  alignItems: "center",
                }}
              >
                <Search
                  size={16}
                  aria-hidden="true"
                  style={{
                    position: "absolute",
                    left: 12,
                    color: "var(--text-3)",
                    pointerEvents: "none",
                  }}
                />
                <input
                  aria-label="Search tests"
                  value={search}
                  onChange={(event) => filter("q", event.target.value)}
                  placeholder="Find test by goal, title, or target…"
                  style={{
                    width: "100%",
                    minHeight: 38,
                    padding: "7px 36px 7px 36px",
                    borderRadius: 6,
                    border: "1px solid var(--border)",
                    background: "var(--surface)",
                    color: "var(--text)",
                    fontSize: 13,
                    outline: "none",
                  }}
                />
                {search ? (
                  <button
                    type="button"
                    aria-label="Clear search query"
                    onClick={() => filter("q", "")}
                    style={{
                      position: "absolute",
                      right: 10,
                      background: "transparent",
                      border: "none",
                      color: "var(--text-3)",
                      cursor: "pointer",
                      padding: 4,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <X size={15} />
                  </button>
                ) : null}
              </div>

              {hasActiveFilters ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearAllFilters}
                  style={{ fontSize: 13, color: "var(--text-2)" }}
                >
                  Clear all filters
                </Button>
              ) : null}
            </div>
          </div>

          {/* Test List Table */}
          {filteredRuns.length > 0 ? (
            <div className="study-table" role="region" aria-label="Tests directory">
              <div
                className="study-table-heading"
                style={{
                  display: "grid",
                  gridTemplateColumns: "minmax(0, 2fr) minmax(180px, 1.2fr) minmax(140px, 1fr) auto",
                  gap: 16,
                  alignItems: "center",
                  padding: "10px 20px",
                }}
              >
                <span>Test & Testing Goal</span>
                <span>Target & Execution Mode</span>
                <span>Status & Phase</span>
                <span style={{ textAlign: "right", paddingRight: 40 }}>Primary Action</span>
              </div>

              {filteredRuns.map((run) => {
                const action = getPrimaryAction(run.status, run.id);
                const isAwaiting = run.status === "awaiting_human";
                const isFeatureMode = run.configuration_snapshot.execution_mode === "deep_feature_v1";
                const targetName = textValue(run.target_snapshot.name, "Target");
                const targetEnv = textValue(run.target_snapshot.environment, "Environment");
                const defaultRowLink = `/runs/${run.id}/${isAwaiting ? "human-action" : "overview"}`;

                return (
                  <div
                    className="deletable-row"
                    key={run.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      borderBottom: "1px solid var(--border)",
                      background: isAwaiting ? "rgba(243, 205, 136, 0.04)" : "transparent",
                    }}
                  >
                    <div
                      style={{
                        flex: 1,
                        minWidth: 0,
                        display: "grid",
                        gridTemplateColumns: "minmax(0, 2fr) minmax(180px, 1.2fr) minmax(140px, 1fr) auto",
                        gap: 16,
                        alignItems: "center",
                        padding: "16px 20px",
                      }}
                    >
                      {/* Column 1: Test & Goal */}
                      <div style={{ minWidth: 0 }}>
                        <Link
                          to={defaultRowLink}
                          style={{
                            display: "block",
                            fontSize: 14,
                            fontWeight: 600,
                            color: "var(--text)",
                            lineHeight: 1.4,
                            overflowWrap: "anywhere",
                            textDecoration: "none",
                          }}
                        >
                          {testTitle(run)}
                        </Link>
                        {run.configuration_snapshot.goal ? (
                          <span
                            style={{
                              display: "block",
                              fontSize: 12,
                              color: "var(--text-3)",
                              marginTop: 3,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {testBrief(run.configuration_snapshot)}
                          </span>
                        ) : null}
                        <span
                          className="monospace"
                          style={{
                            display: "inline-block",
                            fontSize: 11,
                            color: "var(--text-3)",
                            marginTop: 4,
                          }}
                        >
                          ID: {run.id.slice(0, 8)}
                        </span>
                      </div>

                      {/* Column 2: Target & Mode */}
                      <div style={{ minWidth: 0, fontSize: 13 }}>
                        <div style={{ fontWeight: 500, color: "var(--text-2)", overflowWrap: "anywhere" }}>
                          {targetName} <span style={{ color: "var(--text-3)" }}>({targetEnv})</span>
                        </div>
                        <div style={{ marginTop: 4 }}>
                          <span
                            style={{
                              display: "inline-block",
                              fontSize: 11,
                              padding: "2px 7px",
                              borderRadius: 4,
                              background: isFeatureMode ? "var(--surface-muted)" : "var(--info-bg)",
                              color: isFeatureMode ? "var(--text-2)" : "var(--primary)",
                              border: "1px solid var(--border)",
                              fontWeight: 500,
                            }}
                          >
                            {isFeatureMode ? "Feature cases" : "Persona journeys"}
                          </span>
                        </div>
                      </div>

                      {/* Column 3: Status Badge & Phase */}
                      <div style={{ minWidth: 0 }}>
                        <TestStatusBadge status={run.status} />
                        <div
                          style={{
                            fontSize: 11,
                            color: isAwaiting ? "var(--warning)" : "var(--text-3)",
                            fontWeight: isAwaiting ? 600 : 400,
                            marginTop: 4,
                          }}
                        >
                          {getRunPhase(run.status)}
                        </div>
                      </div>

                      {/* Column 4: Primary Action */}
                      <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <Link
                          to={action.to}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 6,
                            padding: "6px 14px",
                            borderRadius: 6,
                            fontSize: 12,
                            fontWeight: 650,
                            textDecoration: "none",
                            background:
                              action.variant === "attention"
                                ? "var(--warning-bg)"
                                : action.variant === "primary"
                                ? "var(--primary)"
                                : "var(--surface-muted)",
                            color:
                              action.variant === "attention"
                                ? "var(--warning)"
                                : action.variant === "primary"
                                ? "var(--on-primary)"
                                : "var(--text)",
                            border:
                              action.variant === "attention"
                                ? "1px solid var(--warning-border)"
                                : action.variant === "primary"
                                ? "1px solid var(--primary)"
                                : "1px solid var(--border)",
                            boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
                            whiteSpace: "nowrap",
                            transition: "opacity 120ms ease",
                          }}
                          aria-label={`${action.label} ${testTitle(run)}`}
                        >
                          <span>{action.label}</span>
                          <ArrowUpRight size={13} aria-hidden="true" />
                        </Link>
                      </div>
                    </div>

                    {/* Delete Trigger for lifecycle managers on terminal runs */}
                    {canManageLifecycle(workspace.role) ? (
                      <div style={{ paddingRight: 12 }}>
                        <DeleteAction
                          kind="test"
                          id={run.id}
                          name={testTitle(run)}
                          disabled={!canDeleteTest(run.status)}
                          onDeleted={() => {
                            void state.refetch();
                          }}
                        />
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState
              title={
                allRuns.length > 0
                  ? "No matching tests found"
                  : "No tests yet"
              }
              copy={
                allRuns.length > 0
                  ? `No tests match your current search query${search ? ` "${search}"` : ""} or status filter. Try clearing your filters.`
                  : "Choose an application and authorized target to plan and execute your first test."
              }
              action={
                allRuns.length > 0 ? (
                  <Button variant="secondary" onClick={clearAllFilters}>
                    Clear filters
                  </Button>
                ) : canWriteWorkspace(workspace.role) ? (
                  <Link className="primary-button" to="/applications">
                    Choose application
                  </Link>
                ) : undefined
              }
            />
          )}
        </>
      )}
    </>
  );
}

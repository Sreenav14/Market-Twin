import React, { useState } from "react";
import { Avatar } from "../../components/ui/Avatar";
import {
  CANONICAL_DEMO_DATA,
  ConceptPayload,
} from "../../lib/concept-dataset";
import {
  NeedsYouRow,
  ProgressLine,
  VerdictStrip,
} from "../../components/concept";

export type DashboardState = "live-moment" | "all-clear" | "brand-new";

interface DashboardPageProps {
  data?: ConceptPayload;
  initialState?: DashboardState;
  onNavigate?: (destination: string) => void;
  className?: string;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  data = CANONICAL_DEMO_DATA,
  initialState = "live-moment",
  onNavigate,
  className = "",
}) => {
  const [dashboardState] = useState<DashboardState>(initialState);

  // Determine badge count for "Needs your help"
  const blockedCount = dashboardState === "live-moment" ? 1 : 0;

  return (
    <div
      className={`concept-dashboard-view min-h-screen ${className}`}
      style={{
        backgroundColor: "var(--paper)",
        color: "var(--ink)",
      }}
    >
      {/* Workspace Header 56px */}
      <header
        className="w-full flex items-center justify-between"
        style={{
          height: "56px",
          backgroundColor: "var(--card)",
          borderBottom: "1px solid var(--line)",
          paddingLeft: "32px",
          paddingRight: "32px",
        }}
      >
        <div className="flex items-center gap-8">
          <button
            type="button"
            onClick={() => onNavigate && onNavigate("Dashboard")}
            className="font-sans font-semibold text-lg cursor-pointer"
            style={{ color: "var(--ink)", background: "none", border: "none", padding: 0 }}
          >
            MarketTwin
          </button>

          <nav className="hidden sm:flex items-center gap-6 font-grid-cell">
            {["Dashboard", "Needs your help", "Your apps", "Tests", "Testers", "Settings"].map(
              (item) => {
                const isActive = item === "Dashboard";
                const isNeedsYou = item === "Needs your help";
                return (
                  <button
                    key={item}
                    type="button"
                    onClick={() => onNavigate && onNavigate(item)}
                    className="inline-flex items-center gap-1.5"
                    style={{
                      background: "none",
                      border: "none",
                      padding: "8px 0",
                      cursor: "pointer",
                      color: isActive ? "var(--ink)" : "var(--ink-2)",
                      fontWeight: isActive ? 600 : 400,
                      borderBottom: isActive ? "2px solid var(--ink)" : "none",
                    }}
                  >
                    <span>{item}</span>
                    {isNeedsYou && blockedCount > 0 && (
                      <span
                        className="font-meta-label"
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          padding: "0 6px",
                          height: "18px",
                          borderRadius: "999px",
                          backgroundColor: "var(--ink)",
                          color: "var(--ink-on-dark)",
                          fontSize: "10px",
                          fontWeight: 600,
                        }}
                      >
                        {blockedCount}
                      </span>
                    )}
                  </button>
                );
              }
            )}
          </nav>
        </div>

        <Avatar kind="person" name="Alex Morgan" />
      </header>

      {/* Main Container */}
      <main className="concept-workspace-container" style={{ paddingTop: "32px", paddingBottom: "64px" }}>
        {/* BRAND NEW EMPTY STATE (§7, §7A) */}
        {dashboardState === "brand-new" && (
          <div className="flex flex-col items-center justify-center text-center py-16">
            <h1 className="font-h1-workspace" style={{ color: "var(--ink)", marginBottom: "16px" }}>
              Dashboard
            </h1>
            <h2 className="font-h2-marketing" style={{ color: "var(--ink)", margin: "0 0 16px 0" }}>
              Your dashboard will live here.
            </h2>
            <p className="font-body" style={{ color: "var(--ink-2)", maxWidth: "540px", margin: "0 0 24px 0" }}>
              Add an app and we will test it like a person would, then show you what worked, what broke, and what we could not check.
            </p>
            <button
              type="button"
              onClick={() => onNavigate && onNavigate("Add an app")}
              className="font-button-label transition-colors"
              style={{
                minHeight: "44px",
                padding: "12px 24px",
                borderRadius: 0,
                backgroundColor: "var(--flame-deep)",
                color: "var(--ink-on-dark)",
                border: "1px solid var(--flame-deep)",
                cursor: "pointer",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--flame-deep-hover)")}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "var(--flame-deep)")}
            >
              Add an app
            </button>
          </div>
        )}

        {/* LIVE MOMENT & ALL CLEAR STATES */}
        {dashboardState !== "brand-new" && (
          <>
            {/* Page H1 + Subtitle */}
            <div style={{ marginBottom: "32px" }}>
              <div className="flex items-center gap-3" style={{ marginBottom: "8px" }}>
                <h1 className="font-h1-workspace" style={{ color: "var(--ink)", margin: 0 }}>
                  Dashboard
                </h1>
                <span
                  className="font-meta-label"
                  style={{
                    padding: "4px 10px",
                    borderRadius: "999px",
                    backgroundColor: "var(--notchecked-tint)",
                    color: "var(--notchecked)",
                    border: "1px solid var(--line)",
                  }}
                >
                  Sample data
                </span>
              </div>

              {dashboardState === "live-moment" ? (
                <p className="font-body-small" style={{ color: "var(--ink-2)", margin: 0 }}>
                  Thread & Co. is being tested now. One tester needs your help.
                </p>
              ) : (
                <p className="font-body-small" style={{ color: "var(--ink-2)", margin: 0 }}>
                  No test is running right now.
                </p>
              )}
            </div>

            {/* ALL CLEAR STATE: Sections 1-2 replaced by ONE calm line */}
            {dashboardState === "all-clear" && (
              <div
                className="font-body"
                style={{
                  color: "var(--ink)",
                  marginBottom: "32px",
                }}
              >
                Nothing needs you right now.
              </div>
            )}

            {/* LIVE MOMENT STATE: Section 1 (Needs you) + Section 2 (Happening now) */}
            {dashboardState === "live-moment" && (
              <>
                {/* 1. Needs you */}
                <section style={{ marginBottom: "32px" }}>
                  <h2 className="font-h2-workspace" style={{ color: "var(--ink)", margin: "0 0 16px 0" }}>
                    Needs you
                  </h2>
                  <NeedsYouRow
                    testerName="Priya"
                    taskName="Track an order"
                    waitingMinutes={data.live.priya.waitingMinutes}
                    onHelpClick={() => onNavigate && onNavigate("Watch live")}
                  />
                </section>

                {/* 2. Happening now */}
                <section style={{ marginBottom: "32px" }}>
                  <h2 className="font-h2-workspace" style={{ color: "var(--ink)", margin: "0 0 16px 0" }}>
                    Happening now
                  </h2>
                  <div
                    style={{
                      backgroundColor: "var(--card)",
                      border: "1px solid var(--line)",
                      borderRadius: "10px",
                      padding: "20px",
                      boxShadow: "var(--shadow-soft)",
                    }}
                  >
                    <ProgressLine
                      appName={data.app.name}
                      checkedAttempts={data.live.attemptsDone}
                      totalAttempts={data.totals.attempts}
                      metaText={`Started ${data.live.startedMinutesAgo} minutes ago`}
                      onClick={() => onNavigate && onNavigate("Watch live")}
                    />
                  </div>
                </section>
              </>
            )}

            {/* 3. Your apps */}
            <section style={{ marginBottom: "32px" }}>
              <h2 className="font-h2-workspace" style={{ color: "var(--ink)", margin: "0 0 16px 0" }}>
                Your apps
              </h2>

              <div
                style={{
                  backgroundColor: "var(--card)",
                  border: "1px solid var(--line)",
                  borderRadius: "10px",
                  padding: "20px",
                  boxShadow: "var(--shadow-soft)",
                }}
              >
                <div className="flex items-center justify-between" style={{ marginBottom: "12px" }}>
                  <h3 className="font-h3" style={{ color: "var(--ink)", margin: 0 }}>
                    {data.app.name}
                  </h3>
                  <span className="font-meta-label" style={{ color: "var(--ink-faint)" }}>
                    THREADANDCO.EXAMPLE
                  </span>
                </div>

                <div className="font-body" style={{ fontWeight: 600, color: "var(--ink)", marginBottom: "12px" }}>
                  Not ready yet · Sat 31 Oct 2026
                </div>

                <div className="flex flex-wrap items-center gap-2" style={{ marginBottom: "16px" }}>
                  <span
                    className="font-body-small"
                    style={{
                      padding: "4px 12px",
                      borderRadius: "999px",
                      border: "1px solid var(--line)",
                      color: "var(--ink)",
                    }}
                  >
                    2 of 3 fixed
                  </span>
                  <span
                    className="font-body-small"
                    style={{
                      padding: "4px 12px",
                      borderRadius: "999px",
                      border: "1px solid var(--line)",
                      color: "var(--ink)",
                    }}
                  >
                    1 of 3 still broken
                  </span>
                  <span
                    className="font-body-small"
                    style={{
                      padding: "4px 12px",
                      borderRadius: "999px",
                      border: "1px solid var(--line)",
                      color: "var(--ink)",
                    }}
                  >
                    1 new of 2 current problems
                  </span>
                </div>

                {/* The verdict's problem words earn the card's space */}
                <div style={{ borderTop: "1px solid var(--line)", paddingTop: "12px", marginBottom: "16px" }}>
                  <div className="font-meta-label" style={{ color: "var(--ink-faint)", marginBottom: "8px" }}>
                    PROBLEMS IN THE LATEST TEST
                  </div>
                  <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                    {data.problems.map((problem) => (
                      <li
                        key={problem.id}
                        className="font-body"
                        style={{ display: "flex", gap: "8px", alignItems: "baseline", color: "var(--ink)", padding: "2px 0" }}
                      >
                        <span aria-hidden="true" style={{ color: "var(--broken)", fontWeight: 600 }}>✕</span>
                        {problem.title}
                      </li>
                    ))}
                  </ul>
                </div>

                <div style={{ marginBottom: "20px" }}>
                  <VerdictStrip
                    appName={data.app.name}
                    segments={[
                      { dateLabel: data.previousTest.dateLabel, verdict: null, isFinished: false },
                      { dateLabel: data.testDateLabel, verdict: data.verdict.word, isFinished: true },
                    ]}
                    lastTestDate={data.testDateLabel}
                  />
                </div>

                <button
                  type="button"
                  onClick={() => onNavigate && onNavigate("Test results")}
                  className="font-button-label transition-colors"
                  style={{
                    minHeight: "44px",
                    padding: "10px 18px",
                    borderRadius: 0,
                    backgroundColor: "transparent",
                    border: "1px solid var(--ink)",
                    color: "var(--ink)",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--paper)")}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                >
                  See test results
                </button>
              </div>
            </section>

            {/* 4. Recent tests — a small table, not dot-joined single lines */}
            <section>
              <h2 className="font-h2-workspace" style={{ color: "var(--ink)", margin: "0 0 16px 0" }}>
                Recent tests
              </h2>

              <div
                style={{
                  backgroundColor: "var(--card)",
                  border: "1px solid var(--line)",
                  borderRadius: "10px",
                  boxShadow: "var(--shadow-soft)",
                  overflowX: "auto",
                }}
              >
                <table className="data-table" style={{ minWidth: "560px" }}>
                  <thead>
                    <tr>
                      {["App", "Date", "Status", "Attempts", "Verdict"].map((h) => (
                        <th
                          key={h}
                          scope="col"
                          className="font-meta-label"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="font-grid-cell">
                    <tr style={{ color: "var(--ink)" }}>
                      <td >{data.app.name}</td>
                      <td >{data.testDateLabel}</td>
                      <td >Testing now</td>
                      <td >
                        {data.live.attemptsDone} of {data.totals.attempts} attempts
                      </td>
                      <td style={{ color: "var(--ink-2)" }}>—</td>
                    </tr>
                    <tr style={{ color: "var(--ink-2)" }}>
                      <td >{data.app.name}</td>
                      <td >{data.previousTest.dateLabel}</td>
                      <td >{data.previousTest.status.split(" · ")[0]}</td>
                      <td >{data.previousTest.status.split(" · ")[1]}</td>
                      <td >No verdict</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
};

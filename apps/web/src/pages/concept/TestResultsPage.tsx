import React from "react";
import { Avatar } from "../../components/ui/Avatar";
import {
  CANONICAL_DEMO_DATA,
  ConceptPayload,
} from "../../lib/concept-dataset";
import {
  ContextTabs,
  OutcomeCoverageBar,
  ProofChip,
  ProofTrail,
  StepList,
  TriptychSignature,
  VerdictBlock,
} from "../../components/concept";

interface TestResultsPageProps {
  data?: ConceptPayload;
  onNavigate?: (destination: string) => void;
  className?: string;
}

export const TestResultsPage: React.FC<TestResultsPageProps> = ({
  data = CANONICAL_DEMO_DATA,
  onNavigate,
  className = "",
}) => {
  return (
    <div
      className={`concept-test-results-view min-h-screen ${className}`}
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
                const isActive = item === "Tests";
                return (
                  <button
                    className="concept-section-nav-button"
                    key={item}
                    type="button"
                    onClick={() => onNavigate && onNavigate(item)}
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
                    {item}
                  </button>
                );
              }
            )}
          </nav>
        </div>

        <Avatar kind="person" name="Alex Morgan" />
      </header>

      {/* In-test Context Row + Tabs */}
      <ContextTabs
        appContextText="THREAD & CO. · TEST · SAT 31 OCT 2026"
        activeTab="Test results"
        onTabChange={(tab) => onNavigate && onNavigate(tab)}
      />

      {/* Main Content Container */}
      <main className="concept-workspace-container" style={{ paddingTop: "32px", paddingBottom: "64px" }}>
        {/* Sample data chip */}
        <div className="flex items-center gap-3" style={{ marginBottom: "20px" }}>
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

        {/* 1. VerdictBlock (Full variant, verdict word is H1 of view) */}
        <VerdictBlock
          word={data.verdict.word}
          reason={data.verdict.reason}
          honestInputs={data.verdict.honestInputs}
          isH1={true}
          className="mb-6"
        />

        {/* 2. Three-Looks Strip (Compact variant, 24px margin) */}
        <div style={{ margin: "24px 0 32px 0" }}>
          <TriptychSignature compact={true} />
        </div>

        {/* 3. Coverage Section */}
        <section style={{ marginBottom: "32px" }}>
          <h2
            className="font-h2-workspace"
            style={{ color: "var(--ink)", margin: "0 0 16px 0" }}
          >
            What we checked
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
            <OutcomeCoverageBar totals={data.totals} />
          </div>
        </section>

        {/* 4. Tasks × Testers Grid */}
        <section style={{ marginBottom: "32px" }}>
          <h2
            className="font-h2-workspace"
            style={{ color: "var(--ink)", margin: "0 0 16px 0" }}
          >
            Task by task
          </h2>

          <div
            style={{
              backgroundColor: "var(--card)",
              border: "1px solid var(--line)",
              borderRadius: "10px",
              overflow: "hidden",
              boxShadow: "var(--shadow-soft)",
            }}
          >
            <table
              className="mt-task-table w-full border-collapse font-grid-cell"
              style={{ textAlign: "left" }}
            >
              <thead>
                <tr style={{ borderBottom: "1px solid var(--line)", backgroundColor: "var(--paper)" }}>
                  <th style={{ padding: "16px 20px", color: "var(--ink-faint)" }} className="font-meta-label">
                    TASK
                  </th>
                  <th style={{ padding: "16px 20px" }}>
                    <div className="flex items-center gap-2">
                      <Avatar kind="persona" name="Tom" size="sm" tint="var(--tom)" />
                      <div>
                        <div style={{ fontWeight: 600, color: "var(--ink)" }}>Tom</div>
                        <div className="font-body-small" style={{ fontSize: "12px", color: "var(--ink-2)" }}>Expert</div>
                      </div>
                    </div>
                  </th>
                  <th style={{ padding: "16px 20px" }}>
                    <div className="flex items-center gap-2">
                      <Avatar kind="persona" name="Maya" size="sm" tint="var(--maya)" />
                      <div>
                        <div style={{ fontWeight: 600, color: "var(--ink)" }}>Maya</div>
                        <div className="font-body-small" style={{ fontSize: "12px", color: "var(--ink-2)" }}>First-time user</div>
                      </div>
                    </div>
                  </th>
                  <th style={{ padding: "16px 20px" }}>
                    <div className="flex items-center gap-2">
                      <Avatar kind="persona" name="Priya" size="sm" tint="var(--priya)" />
                      <div>
                        <div style={{ fontWeight: 600, color: "var(--ink)" }}>Priya</div>
                        <div className="font-body-small" style={{ fontSize: "12px", color: "var(--ink-2)" }}>Impatient mobile user</div>
                      </div>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.tasks.map((task) => {
                  const renderCell = (statusKey: "W" | "B" | "C" | "N") => {
                    if (statusKey === "W") {
                      return (
                        <span style={{ color: "var(--works)", fontWeight: 600 }}>
                          ✓ Worked
                        </span>
                      );
                    }
                    if (statusKey === "B") {
                      return (
                        <span style={{ color: "var(--broken)", fontWeight: 600 }}>
                          ✕ Broken
                        </span>
                      );
                    }
                    if (statusKey === "C") {
                      return (
                        <span style={{ color: "var(--couldnot)", fontWeight: 600 }}>
                          ? Could not check
                        </span>
                      );
                    }
                    return (
                      <span style={{ color: "var(--notchecked)", fontWeight: 600 }}>
                        – Not checked
                      </span>
                    );
                  };

                  return (
                    <React.Fragment key={task.n}>
                      <tr style={{ borderBottom: "1px solid var(--line)" }}>
                        <td style={{ padding: "16px 20px", fontWeight: 600, color: "var(--ink)" }}>
                          <span className="font-mono-data" style={{ color: "var(--ink-faint)", marginRight: "8px" }}>
                            {task.n}.
                          </span>
                          {task.name}
                        </td>
                        <td style={{ padding: "16px 20px" }}>{renderCell(task.tom)}</td>
                        <td style={{ padding: "16px 20px" }}>{renderCell(task.maya)}</td>
                        <td style={{ padding: "16px 20px" }}>
                          {renderCell(task.priya)}
                          {task.couldNotReason && (
                            <div className="font-body-small" style={{ color: "var(--ink-2)", marginTop: "4px" }}>
                              ? Could not check — {task.couldNotReason}
                            </div>
                          )}
                        </td>
                      </tr>
                      {task.notCheckedReason && (
                        <tr style={{ borderBottom: "1px solid var(--line)", backgroundColor: "var(--paper)" }}>
                          <td colSpan={4} style={{ padding: "10px 20px", color: "var(--ink-2)" }} className="font-body-small">
                            {task.notCheckedReason}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* 5. Comparison Strip */}
        <section style={{ marginBottom: "32px" }}>
          <div
            className="font-meta-label"
            style={{ color: "var(--ink-faint)", marginBottom: "12px" }}
          >
            SINCE THE LAST TEST ({data.previousTest.dateLabel.toUpperCase()})
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span
              className="font-body-small"
              style={{
                padding: "4px 12px",
                borderRadius: "999px",
                border: "1px solid var(--line)",
                backgroundColor: "var(--card)",
                color: "var(--ink)",
              }}
            >
              Fixed {data.change.fixed}
            </span>
            <span
              className="font-body-small"
              style={{
                padding: "4px 12px",
                borderRadius: "999px",
                border: "1px solid var(--line)",
                backgroundColor: "var(--card)",
                color: "var(--ink)",
              }}
            >
              Still broken {data.change.stillBroken}
            </span>
            <span
              className="font-body-small"
              style={{
                padding: "4px 12px",
                borderRadius: "999px",
                border: "1px solid var(--line)",
                backgroundColor: "var(--card)",
                color: "var(--ink)",
              }}
            >
              New {data.change.new}
            </span>
          </div>
          <div className="font-body-small" style={{ color: "var(--ink-2)", marginTop: "8px" }}>
            The previous test stopped early after 6 of 18 attempts, so it has no verdict.
          </div>
        </section>

        {/* 6. Confirmed Problems */}
        <section style={{ marginBottom: "32px" }}>
          <h2
            className="font-h2-workspace"
            style={{ color: "var(--ink)", margin: "0 0 16px 0" }}
          >
            Problems we confirmed
          </h2>

          <div className="flex flex-col gap-6">
            {/* P1 Card */}
            <article
              style={{
                backgroundColor: "var(--card)",
                border: "1px solid var(--line)",
                borderRadius: "10px",
                padding: "20px",
                boxShadow: "var(--shadow-soft)",
              }}
            >
              <h3 className="font-h3" style={{ color: "var(--ink)", margin: "0 0 4px 0" }}>
                {data.problems[0].title}
              </h3>
              <div
                className="font-meta-label"
                style={{ color: "var(--ink-faint)", marginBottom: "12px" }}
              >
                BUY A T-SHIRT · FOUND BY MAYA, FIRST-TIME USER
              </div>
              <p className="font-body" style={{ color: "var(--ink-2)", margin: "0 0 12px 0" }}>
                {data.problems[0].description}
              </p>
              <ProofChip screenshots={data.problems[0].proof.screenshots} rechecked={true} />
              <ProofTrail totalScreenshots={7} testerName="Maya" />

              <div style={{ marginTop: "16px", borderTop: "1px solid var(--line)", paddingTop: "12px" }}>
                <StepList
                  steps={data.mayaSteps}
                  failedStepIndex={data.problems[0].failedStep}
                  mode="finished-report"
                />
              </div>
            </article>

            {/* P2 Card */}
            <article
              style={{
                backgroundColor: "var(--card)",
                border: "1px solid var(--line)",
                borderRadius: "10px",
                padding: "20px",
                boxShadow: "var(--shadow-soft)",
              }}
            >
              <h3 className="font-h3" style={{ color: "var(--ink)", margin: "0 0 4px 0" }}>
                {data.problems[1].title}
              </h3>
              <div
                className="font-meta-label"
                style={{ color: "var(--ink-faint)", marginBottom: "12px" }}
              >
                SEE AN ERROR WHEN THE EMAIL IS ALREADY USED · FOUND BY MAYA, FIRST-TIME USER
              </div>
              <p className="font-body" style={{ color: "var(--ink-2)", margin: "0 0 12px 0" }}>
                {data.problems[1].description}
              </p>
              <ProofChip screenshots={null} rechecked={true} />
              <ProofTrail totalScreenshots={null} testerName="Maya" />
            </article>

            {/* Seen once note */}
            <div
              className="font-body-small"
              style={{ color: "var(--ink-2)", marginTop: "4px" }}
            >
              Seen once, not counted as a problem: search suggestions flicker (Tom).
            </div>
          </div>
        </section>

        {/* 7. Feelings Section: "How it felt" */}
        <section style={{ marginBottom: "32px" }}>
          <h2
            className="font-h2-workspace"
            style={{ color: "var(--ink)", margin: "0 0 16px 0" }}
          >
            How it felt
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
            {data.feelings.map((feeling, idx) => {
              const attributionMap = {
                maya: "MAYA · FIRST-TIME USER · BUY A T-SHIRT",
                tom: "TOM · EXPERT · SEE AN ERROR WHEN THE EMAIL IS ALREADY USED",
                priya: "PRIYA · IMPATIENT MOBILE USER · SEARCH FOR A T-SHIRT AND USE FILTERS",
              };
              const attribution = attributionMap[feeling.tester];

              return (
                <div
                  key={idx}
                  style={{
                    paddingTop: idx > 0 ? "16px" : 0,
                    paddingBottom: idx < data.feelings.length - 1 ? "16px" : 0,
                    borderBottom:
                      idx < data.feelings.length - 1
                        ? "1px solid var(--line)"
                        : "none",
                  }}
                >
                  <blockquote
                    className="font-quote"
                    style={{ margin: "0 0 8px 0", color: "var(--ink)" }}
                  >
                    &ldquo;{feeling.quote}&rdquo;
                  </blockquote>
                  <div
                    className="font-meta-label"
                    style={{ color: "var(--ink-2)" }}
                  >
                    {attribution}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* 8. What we did not check */}
        <section>
          <h2
            className="font-h2-workspace"
            style={{ color: "var(--ink)", margin: "0 0 16px 0" }}
          >
            What we did not check
          </h2>

          <ul
            className="font-body flex flex-col gap-3"
            style={{
              listStyle: "none",
              margin: 0,
              padding: 0,
              color: "var(--ink)",
            }}
          >
            <li>
              1 attempt could not be checked. Priya&apos;s search timed out on her connection.
            </li>
            <li>
              Task 3 for Tom and Priya. The plan gave this task to Maya only.
            </li>
            <li>
              Track an order for Tom and Maya. Needs a real order email, which the plan did not include.
            </li>
          </ul>
        </section>
      </main>
    </div>
  );
};

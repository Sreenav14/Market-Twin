import { useEffect } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, RefreshCw, ExternalLink } from "lucide-react";
import { RunContext } from "../../layouts/RunLayout";
import { JourneyDetail, request } from "../../lib/api";
import { findingClassification } from "../../lib/results";
import {
  assertionObservation,
  initialJourneyStep,
  journeyBlocker,
  journeyIdentity,
} from "../../lib/journeyPresentation";
import { ArtifactEvidence } from "./FindingDetailPage";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";

export function JourneyDetailPage() {
  const { run, user } = useOutletContext<RunContext>();
  const { journeyId = "" } = useParams();
  const [parameters, setParameters] = useSearchParams();
  const requestedStep = parameters.get("step");
  const stepId = Number(requestedStep);
  const selected = Number.isSafeInteger(stepId) && stepId > 0 ? stepId : null;

  const query = useInfiniteQuery({
    queryKey: ["journey-detail", user.id, run.id, journeyId],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) =>
      request<JourneyDetail>(
        `/api/v1/test-runs/${run.id}/journeys/${journeyId}?after_step=${pageParam}`,
        { signal }
      ),
    getNextPageParam: (page, _pages, cursor, cursors) => {
      const next = page.next_after_step;
      return next !== null && next > cursor && !cursors.includes(next) ? next : undefined;
    },
  });

  const loadedSteps = query.data?.pages.flatMap((page) => page.steps) ?? [];
  const searchingForStep = selected !== null && !loadedSteps.some((item) => item.id === selected);
  const autoLoadLimit = (query.data?.pages.length ?? 0) >= 50;

  useEffect(() => {
    if (searchingForStep && query.hasNextPage && !query.isFetching && !query.isError && !autoLoadLimit) {
      void query.fetchNextPage();
    }
  }, [searchingForStep, query.hasNextPage, query.isFetching, query.isError,
      query.fetchNextPage, autoLoadLimit]);

  if (query.isPending) return <LoadingPanel label="Loading recorded journey" />;
  if (!query.data)
    return (
      <ErrorPanel
        message={query.error?.message ?? "This journey could not be loaded."}
        action={<Button onClick={() => void query.refetch()}>Try again</Button>}
      />
    );

  const pages = query.data.pages;
  const { journey, findings } = pages[0];

  if (pages.some((page) => page.journey.execution_id !== journey.execution_id))
    return (
      <ErrorPanel
        message="This journey has a new execution attempt. Refresh to view its evidence."
        action={<Button onClick={() => void query.refetch()}>Refresh journey</Button>}
      />
    );

  const steps = loadedSteps;
  const artifacts = pages.flatMap((page) => page.artifacts);
  const step =
    steps.find((item) => item.id === selected) ??
    (requestedStep === null ? initialJourneyStep(steps) : undefined);
  const identity = journeyIdentity(
    journey,
    run.configuration_snapshot.execution_mode === "deep_feature_v1"
  );
  const observation = assertionObservation(step?.observation_summary ?? null);
  const blocker = journeyBlocker(journey, step);
  const stepArtifacts = step ? artifacts.filter((item) => item.step_id === step.id) : [];
  const screenshot = stepArtifacts.find(
    (item) => item.kind === "viewport" && item.artifact_type === "screenshot"
  );
  const entries = Array.isArray(journey.result?.criterion_evidence)
    ? journey.result.criterion_evidence.filter(
        (item): item is { criterion: string; status: string } =>
          typeof item === "object" &&
          item !== null &&
          typeof item.criterion === "string" &&
          typeof item.status === "string"
      )
    : [];

  return (
    <section>
      <Link className="back-link" to={`/runs/${run.id}/journeys`}>
        ← All journeys
      </Link>

      <div className="journey-header-card">
        <div className="section-heading">
          <div>
            <h2>
              {identity.discovery ? "Browser discovery" : journey.mission_title}
            </h2>
            <p className="muted">
              {identity.discovery
                ? "Inspect the authorized target before generating test cases; request assistance only if a challenge is encountered."
                : journey.mission_objective}
            </p>
          </div>
          <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
            <StatusBadge status={journey.execution_status ?? "not started"} />
            <Button
              variant="secondary"
              disabled={query.isFetching}
              onClick={() => void query.refetch()}
            >
              Refresh
            </Button>
          </div>
        </div>

        <div className="journey-header-meta">
          <span className="journey-meta-chip">
            Executor: {identity.executor}
            {identity.caseId ? ` · Case ${identity.caseId}` : ""}
          </span>
          <span className="journey-meta-chip">
            Attempt {journey.attempt_number ?? "not started"}
          </span>
          <span className="journey-meta-chip">
            {journey.step_count} recorded steps
          </span>
          {!identity.discovery ? (
            <span className="journey-meta-chip">
              Product outcome:{" "}
              <StatusBadge status={journey.outcome ?? "not recorded"} />
            </span>
          ) : null}
        </div>

        {typeof run.target_snapshot.base_url === "string" ? (
          <p style={{ marginTop: "12px", fontSize: "13px" }}>
            <strong>Target environment:</strong> {run.target_snapshot.base_url}
          </p>
        ) : null}

        <nav
          aria-label="Journey investigation"
          style={{ display: "flex", gap: "12px", marginTop: "12px" }}
        >
          <Link className="text-link" to={`/runs/${run.id}/evidence`}>
            Browse recorded evidence
          </Link>
          <span aria-hidden="true">·</span>
          <Link className="text-link" to={`/runs/${run.id}/human-action`}>
            Human Assistance history
          </Link>
        </nav>
      </div>

      {journey.error_message ? (
        <p className="error-text" role="alert">
          {journey.error_message}
        </p>
      ) : null}
      {blocker ? (
        <p className="inline-note" role="status">
          {blocker}
        </p>
      ) : null}

      <div className="journey-evidence-grid">
        <div>
          <h3>Browser Steps</h3>
          <ol className="journey-step-list">
            {steps.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={`journey-step ${step?.id === item.id ? "selected" : ""}`}
                  data-status={item.status}
                  aria-pressed={step?.id === item.id}
                  onClick={() => setParameters((previous) => {
                    const next = new URLSearchParams(previous);
                    next.set("step", String(item.id));
                    return next;
                  })}
                >
                  <div className="journey-step-header">
                    <span className="journey-step-tag">
                      Step {item.step_number} · {item.action_type.replaceAll("_", " ")}
                    </span>
                    <StatusBadge status={item.status} />
                  </div>
                  <strong>{item.action_summary}</strong>
                </button>
              </li>
            ))}
          </ol>
          {!steps.length ? (
            <EmptyState
              title="No browser steps recorded"
              copy="A planned journey does not imply that browser execution occurred."
            />
          ) : null}
          {query.hasNextPage ? (
            <Button
              variant="secondary"
              disabled={query.isFetchingNextPage}
              onClick={() => void query.fetchNextPage()}
              style={{ marginTop: "14px", width: "100%" }}
            >
              {query.isFetchingNextPage ? "Loading…" : "Load more steps"}
            </Button>
          ) : null}
          {query.isFetchNextPageError ? (
            <ErrorPanel
              message="The next steps could not be loaded. Your recorded evidence is still available."
              action={<Button onClick={() => void query.fetchNextPage()}>Retry loading steps</Button>}
            />
          ) : null}
        </div>

        <aside
          className="journey-selected-evidence"
          aria-label="Selected step evidence"
        >
          <h3>
            {step
              ? `Step ${step.step_number} Evidence · ${step.action_type.replaceAll(
                  "_",
                  " "
                )}`
              : "Step Evidence"}
          </h3>

          {step ? (
            <div className="journey-context-box">
              <p>
                <strong>What:</strong> {step.action_summary}
              </p>
              <p>
                <strong>Who:</strong> {identity.executor}
              </p>
              <p>
                <strong>Why:</strong>{" "}
                {identity.discovery
                  ? "Inspect the authorized page before planning."
                  : journey.mission_objective}
              </p>
            </div>
          ) : requestedStep !== null ? (
            <p className="inline-note" role="status">
              {selected === null
                ? "This step link is invalid. Choose a recorded step from the list."
                : query.isFetchingNextPage || (query.hasNextPage && !autoLoadLimit && !query.isError)
                  ? "Finding the linked step in recorded evidence…"
                  : query.hasNextPage
                    ? "The linked step has not been located yet. Load more steps to continue searching."
                    : "This step was not found in the recorded journey. It may belong to a different execution attempt."}
            </p>
          ) : null}

          {observation ? (
            <div className="journey-assertion-card">
              <span className="section-label">Assertion Evaluation</span>
              <dl>
                <dt>Assertion</dt>
                <dd>
                  {observation.id} · {observation.oracle}
                </dd>
                <dt>Expected</dt>
                <dd>
                  <code>{observation.expected}</code>
                </dd>
                <dt>Observed</dt>
                <dd>
                  <code>{observation.observed}</code>
                </dd>
                <dt>Result</dt>
                <dd>
                  <StatusBadge status={observation.status} />
                </dd>
                {observation.reason ? (
                  <>
                    <dt>Reason</dt>
                    <dd>{observation.reason}</dd>
                  </>
                ) : null}
              </dl>
            </div>
          ) : step?.observation_summary ? (
            <p style={{ fontSize: "13px", color: "var(--text-2)" }}>
              {step.observation_summary}
            </p>
          ) : null}

          {screenshot ? (
            <div className="journey-screenshot-box">
              <ArtifactEvidence
                key={screenshot.id}
                runId={run.id}
                artifactId={screenshot.id}
                autoLoad
              />
            </div>
          ) : (
            <p className="muted" style={{ margin: "16px 0" }}>
              Evidence unavailable for this step.
            </p>
          )}

          {stepArtifacts
            .filter((item) => item.id !== screenshot?.id)
            .map((item) => (
              <details key={item.id} className="panel" style={{ marginTop: "12px" }}>
                <summary>{item.kind?.replaceAll("_", " ") ?? item.artifact_type}</summary>
                <ArtifactEvidence runId={run.id} artifactId={item.id} />
              </details>
            ))}

          {pages.some((page) => page.artifacts_truncated) ? (
            <p className="inline-note">
              Artifact metadata exceeded this page's limit. Request fewer steps to
              inspect the remainder.
            </p>
          ) : null}
        </aside>
      </div>

      <details className="panel" style={{ marginTop: "24px" }}>
        <summary>
          {identity.discovery
            ? "Discovery checks"
            : identity.featureCase
            ? "Planned assertions"
            : "Reported criteria"}
        </summary>
        <p className="muted">
          {identity.discovery
            ? "Discovery prepares page context for planning; it does not execute a test case or verify an identity unless a separate policy was configured."
            : identity.featureCase
            ? "These expectations belong to the frozen case. Select an assertion step to inspect its recorded result."
            : "These are the simulated user's reports. Verified findings appear separately below."}
        </p>
        <ul>
          {(identity.discovery ? [] : journey.success_criteria).map((criterion) => (
            <li key={criterion}>
              {criterion}
              {identity.featureCase ? null : (
                <>
                  {" "}
                  <StatusBadge
                    status={
                      entries.find((entry) => entry.criterion === criterion)
                        ?.status ?? "not reported"
                    }
                  />
                </>
              )}
            </li>
          ))}
        </ul>
      </details>

      <h3 style={{ marginTop: "28px" }}>Linked Findings</h3>
      {findings.length ? (
        findings.map((finding) => (
          <article className="panel" key={finding.id} style={{ marginTop: "12px" }}>
            <p className="section-label">{findingClassification(finding)}</p>
            <Link to={`/runs/${run.id}/findings/${finding.id}`}>
              {finding.title}
            </Link>
            <p>{finding.summary}</p>
          </article>
        ))
      ) : (
        <p className="muted">
          No linked findings recorded. This does not establish that the journey passed.
        </p>
      )}
    </section>
  );
}

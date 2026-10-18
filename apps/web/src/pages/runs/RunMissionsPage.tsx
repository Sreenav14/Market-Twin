import { useQuery } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";
import { RunContext } from "../../layouts/RunLayout";
import { api } from "../../lib/api";
import { terminalTestStatuses } from "../../lib/results";
import { countLabels, groupJourneys, simulatedTesterJourneys } from "../../lib/testerWork";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";

export function RunMissionsPage() {
  const { run, user } = useOutletContext<RunContext>();
  const isDeep = run.configuration_snapshot.execution_mode === "deep_feature_v1";
  const journeys = useQuery({
    queryKey: ["run-journeys", user.id, run.id],
    queryFn: ({ signal }) => api.getRunJourneys(run.id, signal),
    refetchInterval: terminalTestStatuses.has(run.status) ? false : 5_000,
  });
  const missions = journeys.data ? groupJourneys(simulatedTesterJourneys(journeys.data, isDeep), (journey) => journey.mission_title) : [];
  return (
    <section aria-labelledby="testing-goals-heading">
      <div className="section-heading">
        <div>
          <h2 id="testing-goals-heading">Testing goals</h2>
          <p className="muted">The goals each simulated tester attempted in this test, with the success criteria saved for them.</p>
        </div>
      </div>
      {isDeep ? (
        <EmptyState title="Feature Cases do not use testing goals" copy="Each Feature Case is a planned check listed under Journeys, with its own steps and evidence." />
      ) : journeys.isPending ? <LoadingPanel label="Loading testing goals" /> : journeys.isError ? <ErrorPanel message={journeys.error.message} action={<Button variant="secondary" onClick={() => void journeys.refetch()}>Try again</Button>} /> : !missions.length ? (
        <EmptyState title="No testing goals planned yet" copy={run.status === "draft" ? "Start this test to generate its plan." : "Goals appear once the planner saves its assignments."} />
      ) : (
        <div className="run-records">
          {missions.map((group) => {
            const first = group.journeys[0];
            return (
              <article className="panel run-record" key={group.key}>
                <h3>{first.mission_title}</h3>
                <p>{first.mission_objective}</p>
                {first.success_criteria.length ? (
                  <>
                    <h4>Success criteria</h4>
                    <ul>{first.success_criteria.map((criterion, index) => <li key={index}>{criterion}</li>)}</ul>
                  </>
                ) : null}
                <dl className="definition-list">
                  <div><dt>Testers</dt><dd>{[...new Set(group.journeys.map((journey) => journey.persona_name))].join(", ")}</dd></div>
                  <div><dt>Execution</dt><dd>{countLabels(group.journeys.map((journey) => journey.execution_status))}</dd></div>
                  <div><dt>Recorded outcome</dt><dd>{countLabels(group.journeys.map((journey) => journey.outcome))}</dd></div>
                </dl>
                <ul>
                  {group.journeys.map((journey) => (
                    <li key={journey.id}><Link className="text-link" to={`/runs/${run.id}/journeys/${journey.id}`}>{journey.persona_name} · inspect steps and evidence</Link></li>
                  ))}
                </ul>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

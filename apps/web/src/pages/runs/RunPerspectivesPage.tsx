import { useQuery } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";
import { RunContext } from "../../layouts/RunLayout";
import { api } from "../../lib/api";
import { terminalTestStatuses } from "../../lib/results";
import { countLabels, groupJourneys, simulatedTesterJourneys } from "../../lib/testerWork";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";

export function RunPerspectivesPage() {
  const { run, user } = useOutletContext<RunContext>();
  const isDeep = run.configuration_snapshot.execution_mode === "deep_feature_v1";
  const journeys = useQuery({
    queryKey: ["run-journeys", user.id, run.id],
    queryFn: ({ signal }) => api.getRunJourneys(run.id, signal),
    refetchInterval: terminalTestStatuses.has(run.status) ? false : 5_000,
  });
  const testers = journeys.data ? groupJourneys(simulatedTesterJourneys(journeys.data, isDeep), (journey) => journey.persona_name) : [];
  return (
    <section aria-labelledby="simulated-testers-heading">
      <div className="section-heading">
        <div>
          <h2 id="simulated-testers-heading">Simulated testers</h2>
          <p className="muted">Hypothetical testing perspectives saved for this test. They are not human research participants and do not represent customer opinion.</p>
        </div>
      </div>
      {isDeep ? (
        <EmptyState title="Feature Cases do not use simulated testers" copy="Feature Cases run planned checks with a deterministic browser executor. Open Journeys to inspect their steps and evidence." />
      ) : journeys.isPending ? <LoadingPanel label="Loading simulated testers" /> : journeys.isError ? <ErrorPanel message={journeys.error.message} action={<Button variant="secondary" onClick={() => void journeys.refetch()}>Try again</Button>} /> : !testers.length ? (
        <EmptyState title="No simulated testers planned yet" copy={run.status === "draft" ? "Start this test to generate its plan." : "Testers appear once the planner saves its assignments."} />
      ) : (
        <div className="run-records">
          {testers.map((group) => {
            const first = group.journeys[0];
            return (
              <article className="panel run-record" key={group.key}>
                <h3>{first.persona_name}</h3>
                <p>{first.persona_perspective}</p>
                <p className="muted">{group.journeys.length} planned journey{group.journeys.length === 1 ? "" : "s"}</p>
                <dl className="definition-list">
                  <div><dt>Execution</dt><dd>{countLabels(group.journeys.map((journey) => journey.execution_status))}</dd></div>
                  <div><dt>Recorded outcome</dt><dd>{countLabels(group.journeys.map((journey) => journey.outcome))}</dd></div>
                </dl>
                <ul>
                  {group.journeys.map((journey) => (
                    <li key={journey.id}><Link className="text-link" to={`/runs/${run.id}/journeys/${journey.id}`}>{journey.mission_title}</Link></li>
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

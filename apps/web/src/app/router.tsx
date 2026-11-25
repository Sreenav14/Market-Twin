import { Link, Navigate, Route, Routes, useLocation, useSearchParams } from "react-router-dom";

import { CurrentUser } from "../lib/api";
import { AppShell } from "../layouts/AppShell";
import { RunLayout } from "../layouts/RunLayout";
import { SettingsLayout } from "../layouts/SettingsLayout";
import { WorkspaceDashboardPage } from "../pages/concept/WorkspaceDashboardPage";
import { RunActivityPage } from "../pages/runs/RunActivityPage";
import { ApplicationsPage } from "../pages/applications/ApplicationsPage";
import { NewApplicationPage } from "../pages/applications/NewApplicationPage";
import { ApplicationOverviewPage } from "../pages/applications/ApplicationOverviewPage";
import { ApplicationKnowledgePage } from "../pages/knowledge/ApplicationKnowledgePage";
import { IngestionPage } from "../pages/knowledge/IngestionPage";
import { KnowledgeListPage } from "../pages/knowledge/KnowledgeListPage";
import { KnowledgeEntryPage } from "../pages/knowledge/KnowledgeEntryPage";
import { ApplicationPersonasPage } from "../pages/applications/ApplicationPersonasPage";
import { ApplicationRunsPage } from "../pages/applications/ApplicationRunsPage";
import { EditApplicationPage } from "../pages/applications/EditApplicationPage";
import { TargetsPage } from "../pages/targets/TargetsPage";
import { NewTargetPage } from "../pages/targets/NewTargetPage";
import { TargetOverviewPage } from "../pages/targets/TargetOverviewPage";
import { TargetAuthorizationPage } from "../pages/targets/TargetAuthorizationPage";
import { EditTargetPage } from "../pages/targets/EditTargetPage";
import { TargetNetworkPolicyPage } from "../pages/targets/TargetNetworkPolicyPage";
import { RunsPage } from "../pages/runs/RunsPage";
import { NewRunPage } from "../pages/runs/NewRunPage";
import { UiSlopPage } from "../pages/runs/UiSlopPage";
import { RunOverviewPage } from "../pages/runs/RunOverviewPage";
import { RunBoardPage } from "../pages/runs/RunBoardPage";
import { AgentPromptsPage } from "../pages/runs/AgentPromptsPage";
import { RunPerspectivesPage } from "../pages/runs/RunPerspectivesPage";
import { RunMissionsPage } from "../pages/runs/RunMissionsPage";
import { RunJourneysPage } from "../pages/runs/RunJourneysPage";
import { RunEvaluationPage } from "../pages/runs/RunEvaluationPage";
import { JourneyDetailPage } from "../pages/runs/JourneyDetailPage";
import { RunFindingsPage } from "../pages/runs/RunFindingsPage";
import { FindingDetailPage } from "../pages/runs/FindingDetailPage";
import { RunEvidencePage } from "../pages/runs/RunEvidencePage";
import { EvidenceDetailPage } from "../pages/runs/EvidenceDetailPage";
import { ProfileSettingsPage } from "../pages/settings/ProfileSettingsPage";
import { WorkspaceSettingsPage } from "../pages/settings/WorkspaceSettingsPage";
import { ForbiddenPage } from "../pages/system/ForbiddenPage";
import { NotFoundPage } from "../pages/system/NotFoundPage";
import { UnexpectedErrorPage } from "../pages/system/UnexpectedErrorPage";

const summaryViews = {
  findings: ["Findings", RunFindingsPage],
  evaluation: ["Evaluation", RunEvaluationPage],
  perspectives: ["Perspectives", RunPerspectivesPage],
} as const;
const activityViews = {
  board: ["Checks ledger", RunBoardPage],
  journeys: ["Journeys", RunJourneysPage],
  missions: ["Missions", RunMissionsPage],
  agents: ["Testers", AgentPromptsPage],
} as const;

function RunSection({ section }: { section: "summary" | "activity" }) {
  const [search] = useSearchParams();
  const view = search.get("view");
  const match = Object.entries(section === "summary" ? summaryViews : activityViews)
    .find(([key]) => key === view);
  if (!match) return section === "summary" ? <RunOverviewPage /> : <RunActivityPage view="activity" />;
  const [, [title, Detail]] = match;
  return <>
    <nav className="button-row" aria-label={`${title} navigation`}>
      <Link to={section === "summary" ? "." : "../activity"}>Back to {section === "summary" ? "Summary" : "Activity"}</Link>
    </nav>
    <Detail />
  </>;
}

function RunBookmark({ pathname, view, fallbackHash }: {
  pathname: string;
  view?: string;
  fallbackHash?: string;
}) {
  const location = useLocation();
  const search = new URLSearchParams(location.search);
  if (view) search.set("view", view);
  return <Navigate replace state={location.state} to={{
    pathname, search: search.toString(), hash: location.hash || fallbackHash,
  }} />;
}

export function AuthenticatedRouter({
  user,
  onLogout,
}: {
  user: CurrentUser;
  onLogout: () => Promise<void>;
}) {
  return (
    <Routes>
      <Route element={<AppShell user={user} onLogout={onLogout} />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<Navigate to="/dashboard" replace />} />
        <Route
          path="/auth/callback"
          element={<Navigate to="/dashboard" replace />}
        />
        <Route path="/overview" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<WorkspaceDashboardPage />} />
        <Route path="/results" element={<Navigate to="/runs?status=completed" replace />} />
        <Route path="/test-results" element={<Navigate to="/runs?status=completed" replace />} />
        <Route path="/watch" element={<Navigate to="/dashboard" replace />} />
        <Route path="/watch-live" element={<Navigate to="/dashboard" replace />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/knowledge" element={<KnowledgeListPage />} />
        <Route path="/knowledge/add" element={<IngestionPage />} />
        <Route path="/ingestion" element={<Navigate to="/knowledge/add" replace />} />
        <Route path="/knowledge/review" element={<KnowledgeListPage />} />
        <Route path="/knowledge/review/:entryId" element={<KnowledgeEntryPage />} />
        <Route path="/applications/new" element={<NewApplicationPage />} />
        <Route
          path="/applications/:applicationId"
          element={<ApplicationOverviewPage />}
        />
        <Route
          path="/applications/:applicationId/knowledge"
          element={<ApplicationKnowledgePage />}
        />
        <Route
          path="/applications/:applicationId/edit"
          element={<EditApplicationPage />}
        />
        <Route
          path="/applications/:applicationId/runs"
          element={<ApplicationRunsPage />}
        />
        <Route
          path="/applications/:applicationId/personas"
          element={<ApplicationPersonasPage />}
        />
        <Route
          path="/applications/:applicationId/targets"
          element={<TargetsPage />}
        />
        <Route
          path="/applications/:applicationId/targets/new"
          element={<NewTargetPage />}
        />
        <Route path="/targets/:targetId" element={<TargetOverviewPage />} />
        <Route
          path="/targets/:targetId/authorization"
          element={<TargetAuthorizationPage />}
        />
        <Route path="/targets/:targetId/edit" element={<EditTargetPage />} />
        <Route
          path="/targets/:targetId/network"
          element={<TargetNetworkPolicyPage />}
        />
        <Route
          path="/applications/:applicationId/runs/new"
          element={<NewRunPage />}
        />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/new" element={<UiSlopPage />} />
        <Route path="/ui-slop" element={<Navigate to="/runs/new?mode=slop" replace />} />
        <Route path="/agents" element={<Navigate to="/applications" replace />} />
        <Route path="/runs/:runId" element={<RunLayout />}>
          <Route index element={<RunSection section="summary" />} />
          {["overview", "report", "results"].map(path =>
            <Route key={path} path={path} element={<RunBookmark pathname=".." />} />,
          )}
          {Object.keys(summaryViews).map(view =>
            <Route key={view} path={view} element={<RunBookmark pathname=".." view={view} />} />,
          )}
          {Object.keys(activityViews).map(view =>
            <Route key={view} path={view} element={<RunBookmark pathname="../activity" view={view} />} />,
          )}
          <Route path="journeys/:journeyId" element={<JourneyDetailPage />} />
          <Route path="activity" element={<RunSection section="activity" />} />
          <Route path="watch" element={<RunActivityPage />} />
          <Route path="findings/:findingId" element={<FindingDetailPage />} />
          <Route path="evidence" element={<RunEvidencePage />} />
          <Route path="evidence/:artifactId" element={<EvidenceDetailPage />} />
          <Route path="human-action" element={<RunBookmark pathname="../watch" fallbackHash="#human-action-heading" />} />
        </Route>
        <Route path="/settings" element={<SettingsLayout />}>
          <Route index element={<Navigate to="profile" replace />} />
          <Route path="profile" element={<ProfileSettingsPage />} />
          <Route path="workspace" element={<WorkspaceSettingsPage />} />
          <Route path="members" element={<Navigate to="../workspace" replace />} />
          <Route path="security" element={<Navigate to="../profile" replace />} />
        </Route>
        <Route path="/403" element={<ForbiddenPage />} />
        <Route path="/error" element={<UnexpectedErrorPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

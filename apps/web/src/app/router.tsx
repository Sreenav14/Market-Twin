import { Navigate, Route, Routes } from "react-router-dom";

import { CurrentUser } from "../lib/api";
import { AppShell } from "../layouts/AppShell";
import { RunLayout } from "../layouts/RunLayout";
import { SettingsLayout } from "../layouts/SettingsLayout";
import { OverviewPage } from "../pages/overview/OverviewPage";
import { ApplicationsPage } from "../pages/applications/ApplicationsPage";
import { NewApplicationPage } from "../pages/applications/NewApplicationPage";
import { ApplicationOverviewPage } from "../pages/applications/ApplicationOverviewPage";
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
import { RunOverviewPage } from "../pages/runs/RunOverviewPage";
import { RunPerspectivesPage } from "../pages/runs/RunPerspectivesPage";
import { RunMissionsPage } from "../pages/runs/RunMissionsPage";
import { RunJourneysPage } from "../pages/runs/RunJourneysPage";
import { JourneyDetailPage } from "../pages/runs/JourneyDetailPage";
import { RunActivityPage } from "../pages/runs/RunActivityPage";
import { RunFindingsPage } from "../pages/runs/RunFindingsPage";
import { FindingDetailPage } from "../pages/runs/FindingDetailPage";
import { RunEvidencePage } from "../pages/runs/RunEvidencePage";
import { EvidenceDetailPage } from "../pages/runs/EvidenceDetailPage";
import { RunReportPage } from "../pages/runs/RunReportPage";
import { HumanActionPage } from "../pages/runs/HumanActionPage";
import { ProfileSettingsPage } from "../pages/settings/ProfileSettingsPage";
import { WorkspaceSettingsPage } from "../pages/settings/WorkspaceSettingsPage";
import { MembersSettingsPage } from "../pages/settings/MembersSettingsPage";
import { SecuritySettingsPage } from "../pages/settings/SecuritySettingsPage";
import { ForbiddenPage } from "../pages/system/ForbiddenPage";
import { NotFoundPage } from "../pages/system/NotFoundPage";
import { UnexpectedErrorPage } from "../pages/system/UnexpectedErrorPage";

export function AuthenticatedRouter({ user, onLogout }: { user: CurrentUser; onLogout: () => Promise<void> }) {
  return (
    <Routes>
      <Route element={<AppShell user={user} onLogout={onLogout} />}>
        <Route index element={<Navigate to="/overview" replace />} />
        <Route path="/login" element={<Navigate to="/overview" replace />} />
        <Route path="/auth/callback" element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<OverviewPage />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/applications/new" element={<NewApplicationPage />} />
        <Route path="/applications/:applicationId" element={<ApplicationOverviewPage />} />
        <Route path="/applications/:applicationId/edit" element={<EditApplicationPage />} />
        <Route path="/applications/:applicationId/runs" element={<ApplicationRunsPage />} />
        <Route path="/applications/:applicationId/targets" element={<TargetsPage />} />
        <Route path="/applications/:applicationId/targets/new" element={<NewTargetPage />} />
        <Route path="/targets/:targetId" element={<TargetOverviewPage />} />
        <Route path="/targets/:targetId/authorization" element={<TargetAuthorizationPage />} />
        <Route path="/targets/:targetId/edit" element={<EditTargetPage />} />
        <Route path="/targets/:targetId/network" element={<TargetNetworkPolicyPage />} />
        <Route path="/applications/:applicationId/runs/new" element={<NewRunPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunLayout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<RunOverviewPage />} />
          <Route path="perspectives" element={<RunPerspectivesPage />} />
          <Route path="missions" element={<RunMissionsPage />} />
          <Route path="journeys" element={<RunJourneysPage />} />
          <Route path="journeys/:journeyId" element={<JourneyDetailPage />} />
          <Route path="activity" element={<RunActivityPage />} />
          <Route path="findings" element={<RunFindingsPage />} />
          <Route path="findings/:findingId" element={<FindingDetailPage />} />
          <Route path="evidence" element={<RunEvidencePage />} />
          <Route path="evidence/:artifactId" element={<EvidenceDetailPage />} />
          <Route path="report" element={<RunReportPage />} />
          <Route path="human-action" element={<HumanActionPage />} />
        </Route>
        <Route path="/settings" element={<SettingsLayout />}>
          <Route index element={<Navigate to="profile" replace />} />
          <Route path="profile" element={<ProfileSettingsPage />} />
          <Route path="workspace" element={<WorkspaceSettingsPage />} />
          <Route path="members" element={<MembersSettingsPage />} />
          <Route path="security" element={<SecuritySettingsPage />} />
        </Route>
        <Route path="/403" element={<ForbiddenPage />} />
        <Route path="/error" element={<UnexpectedErrorPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

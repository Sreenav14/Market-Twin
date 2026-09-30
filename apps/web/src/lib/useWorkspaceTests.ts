import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { terminalTestStatuses } from "./results";

export function useWorkspaceTests(userId: string, workspaceId: string) {
  return useQuery({
    queryKey: ["workspace-tests", userId, workspaceId],
    queryFn: async () => {
      const applications = await api.listApplications(workspaceId);
      const groups = await Promise.all(
        applications.map((application) => api.listRuns(application.id)),
      );
      return { applications, runs: groups.flat() };
    },
    refetchInterval: (query) =>
      query.state.data?.runs.some(
        (run) => run.status !== "draft" && !terminalTestStatuses.has(run.status),
      )
        ? 5_000
        : false,
  });
}

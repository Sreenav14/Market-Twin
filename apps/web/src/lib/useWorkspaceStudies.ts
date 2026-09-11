import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export function useWorkspaceStudies(userId: string, workspaceId: string) {
  return useQuery({ queryKey: ["workspace-studies", userId, workspaceId], queryFn: async () => {
    const applications = await api.listApplications(workspaceId);
    const groups = await Promise.all(applications.map(application => api.listRuns(application.id)));
    return { applications, runs: groups.flat() };
  } });
}

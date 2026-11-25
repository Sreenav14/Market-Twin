import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useOutletContext, useSearchParams } from "react-router-dom";
import type { AppShellContext } from "../../layouts/AppShell";
import { api } from "../../lib/api";
import { NewRunPage } from "./NewRunPage";

export function UiSlopPage() {
  const { workspace, user } = useOutletContext<AppShellContext>();
  const [params] = useSearchParams();
  const [selected, setSelected] = useState("");
  const apps = useQuery({ queryKey: ["ui-slop-apps", user.id, workspace.id],
    queryFn: () => api.listApplications(workspace.id) });
  return <>
    <h1>New test</h1>
    <p>Choose an application to set up its test.</p>
    <label htmlFor="audit-app">Application</label>
    <select id="audit-app" value={selected} onChange={(event) => setSelected(event.target.value)}>
      <option value="">Choose an application</option>
      {apps.data?.filter((app) => app.status === "active").map((app) =>
        <option key={app.id} value={app.id}>{app.name}</option>)}
    </select>
    {apps.isPending ? <p role="status">Loading applications…</p> : null}
    {apps.isError ? <p role="alert">Could not load applications. <button onClick={() => void apps.refetch()}>Retry</button></p> : null}
    {selected ? <NewRunPage key={selected} applicationIdOverride={selected}
      fixedKind={params.get("mode") === "slop" ? "slop" : undefined} /> : null}
  </>;
}

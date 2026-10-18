import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RunFlowPanel } from "./RunFlowPanel";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("shows discovery before the unstarted feature plan without counting it as a case", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    nodes: [
      { id: "discovery:1", kind: "discovery", label: "Browser discovery", status: "awaiting_human" },
      { id: "meta", kind: "meta", label: "Feature plan", status: "not_started" },
    ], edges: [{ source: "discovery:1", target: "meta" }], revision: "1",
    execution_policy: "once_per_journey",
  }), { status: 200, headers: { "Content-Type": "application/json" } })));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <RunFlowPanel runId="run-1" userId="user-1" runStatus="awaiting_human" reportReady={false} />
  </QueryClientProvider>);
  expect(await screen.findByText("0 cases")).toBeInTheDocument();
  const discovery = screen.getByText("Browser discovery");
  const plan = screen.getByText("Feature plan");
  expect(discovery.compareDocumentPosition(plan) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.queryByText("Feature cases")).not.toBeInTheDocument();
});

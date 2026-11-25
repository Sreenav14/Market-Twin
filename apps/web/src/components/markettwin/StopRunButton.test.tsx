import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { TestRun } from "../../lib/api";
import { StopRunButton } from "./StopRunButton";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function runWith(
  status: TestRun["status"],
  snapshot: Record<string, unknown> = {},
): TestRun {
  return {
    id: "run-1",
    workspace_id: "workspace-1",
    application_id: "app-1",
    target_id: "target-1",
    created_by_user_id: "user-1",
    status,
    target_snapshot: {},
    configuration_snapshot: snapshot,
  };
}

function renderButton(run: TestRun) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <StopRunButton run={run} />
    </QueryClientProvider>,
  );
}

it("renders nothing for a finished or unstarted run", () => {
  for (const status of ["completed", "failed", "cancelled", "draft"] as const) {
    const { container, unmount } = renderButton(runWith(status));
    expect(container).toBeEmptyDOMElement();
    unmount();
  }
});

it("asks for an inline confirmation before recording the stop", () => {
  renderButton(runWith("running"));
  fireEvent.click(screen.getByRole("button", { name: "Stop run" }));
  expect(
    screen.getByText(/everything not yet checked closes as not checked/),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Keep running" }));
  expect(
    screen.queryByText(/everything not yet checked/),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Stop run" })).toBeInTheDocument();
});

it("records the stop and shows the requested state", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        test_run_id: "run-1",
        run_status: "running",
        stop_requested_at: "2026-11-18T20:34:00+00:00",
      }),
      { status: 202, headers: { "Content-Type": "application/json" } },
    ),
  );
  vi.stubGlobal("fetch", fetchMock);
  renderButton(runWith("running"));
  fireEvent.click(screen.getByRole("button", { name: "Stop run" }));
  fireEvent.click(screen.getByRole("button", { name: "Stop run" }));
  expect(await screen.findByText(/Stop requested/)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(url).toBe("/api/v1/test-runs/run-1/stop");
  expect(init.method).toBe("POST");
});

it("shows the requested state when the snapshot already carries the flag", () => {
  renderButton(
    runWith("running", {
      owner_stop: {
        requested_at: "2026-11-18T20:34:00+00:00",
        requested_by: "user-1",
      },
    }),
  );
  expect(screen.getByText(/Stop requested/)).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Stop run" }),
  ).not.toBeInTheDocument();
});

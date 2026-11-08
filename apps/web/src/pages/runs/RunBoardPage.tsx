import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOutletContext } from "react-router-dom";

import { EmptyState } from "../../components/ui/StateViews";
import { InlineAlert } from "../../components/ui/Feedback";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { StackedBar } from "../../components/markettwin/ResultFigures";
import type { BarSegment } from "../../components/markettwin/ResultFigures";
import { api } from "../../lib/api";
import { statusEntry } from "../../lib/status";
import type { HarnessItemStatus } from "../../lib/status";
import type { RunContext } from "../../layouts/RunLayout";

const STATUS_ORDER: HarnessItemStatus[] = [
  "worked",
  "broken",
  "could_not_check",
  "not_checked",
  "blocked",
  "needs_human_login",
  "running",
  "pending",
  "owner_disabled",
];

export function RunBoardPage() {
  const { run } = useOutletContext<RunContext>();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<string | null>(null);

  const board = useQuery({
    queryKey: ["run-board", run.id],
    queryFn: ({ signal }) => api.getRunBoard(run.id, signal),
    retry: false,
    refetchInterval:
      run.status === "running" || run.status === "awaiting_human" ? 2000 : false,
  });

  const disable = useMutation({
    mutationFn: (itemId: string) => api.disableBoardItem(run.id, itemId),
    onSuccess: (data) => {
      queryClient.setQueryData(["run-board", run.id], data);
    },
  });

  if (board.isPending) {
    return (
      <section aria-labelledby="board-heading">
        <div className="section-heading">
          <div>
            <h2 id="board-heading">Board</h2>
            <p className="muted">Loading the board…</p>
          </div>
        </div>
      </section>
    );
  }

  if (board.isError || !board.data) {
    return (
      <section aria-labelledby="board-heading">
        <div className="section-heading">
          <div>
            <h2 id="board-heading">Board</h2>
          </div>
        </div>
        <EmptyState
          title="This run has no board"
          copy="The Board is the work list of an Explore & Test run: every control the tester found, and what happened when it was checked. Runs created with the older run types do not have one."
        />
      </section>
    );
  }

  const data = board.data;
  const checked = (data.counts.worked ?? 0) + (data.counts.broken ?? 0);
  const segments: BarSegment[] = STATUS_ORDER.map((status) => ({
    key: status,
    word: statusEntry("harnessItem", status).word,
    count: data.counts[status] ?? 0,
    tone: statusEntry("harnessItem", status).tone,
  }));
  const visibleItems = filter
    ? data.items.filter((item) => item.status === filter)
    : data.items;
  const canDisable = data.run_status !== "running";

  return (
    <section aria-labelledby="board-heading">
      <div className="section-heading">
        <div>
          <h2 id="board-heading">Board</h2>
          <p className="muted">
            Checked {checked} of {data.total} items. Every control the tester
            found is on this list — nothing is silently dropped.
          </p>
        </div>
      </div>
      {disable.isError ? (
        <InlineAlert severity="error" title="Could not turn the item off" role="alert">
          {disable.error instanceof Error ? disable.error.message : "Please try again."}
        </InlineAlert>
      ) : null}
      <StackedBar
        segments={segments}
        total={data.total}
        unit="items"
        selected={filter}
        onSelect={setFilter}
      />
      {filter ? (
        <p role="status">
          Showing {visibleItems.length} of {data.total} items —{" "}
          {statusEntry("harnessItem", filter).word} only.
        </p>
      ) : null}
      <div className="report-table-scroll">
        <table className="report-task-table">
          <caption>Board items</caption>
          <thead>
            <tr>
              <th scope="col">Item</th>
              <th scope="col">Page</th>
              <th scope="col">Status</th>
              <th scope="col">Why not checked</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.map((item) => (
              <tr key={item.item_id}>
                <td>
                  {item.name || item.role}{" "}
                  <span className="muted">({item.role})</span>
                </td>
                <td className="muted">{item.page_url}</td>
                <td>
                  <StatusBadge status={item.status} source="harnessItem" />
                </td>
                <td className="muted">{item.blocker ?? ""}</td>
                <td>
                  {canDisable && item.status === "pending" ? (
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={disable.isPending}
                      onClick={() => disable.mutate(item.item_id)}
                    >
                      Turn off
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {visibleItems.length === 0 ? (
        <EmptyState
          title="Nothing in this state"
          copy="No board items have this status right now. Clear the filter to see the whole board."
        />
      ) : null}
    </section>
  );
}

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../lib/api";
import { KafkaStatusBadge } from "./KafkaStatusBadge";

afterEach(() => vi.restoreAllMocks());

function renderBadge() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <KafkaStatusBadge />
    </QueryClientProvider>,
  );
}

describe("KafkaStatusBadge", () => {
  it("shows a successful broker check", async () => {
    vi.spyOn(api, "kafkaHealth").mockResolvedValue({
      status: "connected",
      outbox_relay_enabled: true,
    });
    renderBadge();
    expect(await screen.findByText("Kafka connected")).toHaveClass("status-success");
  });

  it("shows an unavailable broker", async () => {
    vi.spyOn(api, "kafkaHealth").mockResolvedValue({
      status: "unavailable",
      outbox_relay_enabled: true,
    });
    renderBadge();
    expect(await screen.findByText("Kafka unavailable")).toHaveClass("status-warning");
  });

  it("warns when the broker is connected but the outbox relay is disabled", async () => {
    vi.spyOn(api, "kafkaHealth").mockResolvedValue({
      status: "connected",
      outbox_relay_enabled: false,
    });
    renderBadge();
    const badge = await screen.findByText("Kafka connected · relay off");
    expect(badge).toHaveClass("status-warning");
    expect(badge).not.toHaveClass("status-success");
  });

  it("shows unknown when the API request fails", async () => {
    vi.spyOn(api, "kafkaHealth").mockRejectedValue(new Error("Offline"));
    renderBadge();
    expect(await screen.findByText("Kafka status unknown")).toHaveClass("status-warning");
  });

  it("explains a missing health endpoint without claiming the broker is down", async () => {
    vi.spyOn(api, "kafkaHealth").mockRejectedValue(new ApiError("Not Found", 404));
    renderBadge();
    expect(await screen.findByText("Kafka status unknown"))
      .toHaveAttribute("title", expect.stringContaining("Restart the Control API"));
  });
});

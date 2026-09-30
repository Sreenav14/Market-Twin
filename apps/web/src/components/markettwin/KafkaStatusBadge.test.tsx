import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
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

  it("shows unavailable when the API request fails", async () => {
    vi.spyOn(api, "kafkaHealth").mockRejectedValue(new Error("Offline"));
    renderBadge();
    expect(await screen.findByText("Kafka unavailable")).toHaveClass("status-warning");
  });
});

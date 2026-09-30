import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../lib/api";

export function KafkaStatusBadge() {
  const health = useQuery({
    queryKey: ["kafka-health"],
    queryFn: ({ signal }) => api.kafkaHealth(signal),
    refetchInterval: 15_000,
    retry: false,
  });
  const connected = !health.isError && health.data?.status === "connected";
  const relayOff = health.data?.outbox_relay_enabled === false;
  const label = health.isPending
    ? "Kafka checking"
    : health.isError
      ? "Kafka status unknown"
      : connected
        ? relayOff ? "Kafka connected · relay off" : "Kafka connected"
        : "Kafka unavailable";
  return (
    <span
      className={`status-badge status-${health.isPending ? "neutral" : connected && !relayOff ? "success" : "warning"}`}
      role="status"
      title={
        health.isError
          ? health.error instanceof ApiError && health.error.status === 404
            ? "The Kafka status endpoint is missing. Restart the Control API to load the current version."
            : "Could not retrieve Kafka status from the Control API. The broker may still be online."
          : health.data?.outbox_relay_enabled === false
          ? "Outbox relay is disabled. Enable it to publish queued run commands."
          : "Kafka broker connectivity. This does not report execution worker availability."
      }
    >
      <span className="status-dot" aria-hidden="true" />
      {label}
    </span>
  );
}

import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";

export function KafkaStatusBadge() {
  const health = useQuery({
    queryKey: ["kafka-health"],
    queryFn: ({ signal }) => api.kafkaHealth(signal),
    refetchInterval: 15_000,
    retry: false,
  });
  const connected = !health.isError && health.data?.status === "connected";
  const label = health.isPending
    ? "Kafka checking"
    : connected
      ? "Kafka connected"
      : "Kafka unavailable";
  return (
    <span
      className={`status-badge status-${health.isPending ? "neutral" : connected ? "success" : "warning"}`}
      role="status"
      title={
        health.data?.outbox_relay_enabled === false
          ? "Outbox relay is disabled. Enable it to publish queued run commands."
          : "Kafka broker connectivity. This does not report execution worker availability."
      }
    >
      <span className="status-dot" aria-hidden="true" />
      {label}
    </span>
  );
}

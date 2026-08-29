export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone =
    normalized === "active" || normalized === "authorized" || normalized === "completed"
      ? "success"
      : normalized === "running" || normalized === "planning" || normalized === "queued"
        ? "info"
        : normalized === "failed" || normalized === "revoked" || normalized === "expired" || normalized === "not authorized"
          ? "danger"
          : "neutral";

  return <span className={`status-badge status-${tone}`}>{status.replaceAll("_", " ")}</span>;
}

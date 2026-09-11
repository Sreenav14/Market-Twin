const success = new Set(["active", "authorized", "completed", "passed", "healthy"]);
const danger = new Set(["failed", "revoked", "expired", "not authorized", "critical", "high"]);
const warning = new Set(["partial", "medium", "timed_out", "policy_blocked", "awaiting_human", "human_action_required", "paused"]);
const info = new Set(["running", "planning", "queued", "evaluating", "generating", "low"]);

export function StatusBadge({ status }: { status: string }) {
  const value = status.toLowerCase();
  const tone = success.has(value) ? "success" : danger.has(value) ? "danger" : warning.has(value) ? "warning" : info.has(value) ? "info" : "neutral";
  return <span className={`status-badge status-${tone}`}><span className="status-dot" aria-hidden="true" />{status.replaceAll("_", " ")}</span>;
}

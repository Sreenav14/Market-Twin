import type { AgentStructure } from "../../lib/agentPrompts";

export function AgentTree({ structure }: { structure: AgentStructure }) {
  return <ol className="agent-tree"><li><strong>{structure.name}</strong> <span className="muted">{structure.agent_type}</span>
    {structure.model_configuration ? <p className="muted">Requested temperature {structure.model_configuration.requested_temperature ?? "not recorded"} · Effective {structure.model_configuration.temperature ?? "provider default / unsupported"}</p> : null}
    {structure.sub_agents.map((child) => <AgentTree key={child.name} structure={child} />)}
  </li></ol>;
}

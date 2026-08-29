import { Icon } from "./Icon";

export function LifecyclePanel({ entityType, entityName }: { entityType: "application" | "target"; entityName: string }) {
  return (
    <section className="danger-zone" aria-labelledby={`${entityType}-lifecycle-title`}>
      <div>
        <p className="eyebrow danger-eyebrow">Lifecycle</p>
        <h2 id={`${entityType}-lifecycle-title`}>{`Archive or delete ${entityType}`}</h2>
        <p>
          MarketTwin preserves historical runs and their evidence. Archive and delete controls will activate only after the Control API defines the safe lifecycle contract for <strong>{entityName}</strong>.
        </p>
      </div>
      <div className="danger-actions">
        <button className="secondary-button" type="button" disabled title="Backend archive/restore API is not implemented yet.">Archive</button>
        <button className="danger-button" type="button" disabled title="Backend delete semantics are not implemented yet."><Icon name="warning" size={15} /> Delete</button>
      </div>
    </section>
  );
}

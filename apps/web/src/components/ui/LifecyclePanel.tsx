import { useNavigate } from "react-router-dom";
import { DeleteAction } from "../markettwin/DeleteAction";

export function LifecyclePanel({ entityType, entityName, entityId, returnTo }: { entityType: "application" | "target"; entityName: string; entityId: string; returnTo: string }) {
  const navigate = useNavigate();
  return (
    <section className="danger-zone" aria-labelledby={`${entityType}-lifecycle-title`}>
      <div>
        <p className="eyebrow danger-eyebrow">Lifecycle</p>
        <h2 id={`${entityType}-lifecycle-title`}>{`Delete ${entityType}`}</h2>
        <p>
          Remove <strong>{entityName}</strong> when you no longer need it. Delete its tests{entityType === "application" ? " and targets" : ""} first.
        </p>
      </div>
      <div className="danger-actions">
        <DeleteAction kind={entityType} id={entityId} name={entityName} onDeleted={() => navigate(returnTo)} />
      </div>
    </section>
  );
}

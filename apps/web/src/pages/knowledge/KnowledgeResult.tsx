import { type ApplicationKnowledgeDraft, type GeneratedSkillDraft, type KnowledgePreviewResponse, type ProcedureArtifactDraft } from "../../lib/api";

function timestamp(seconds: number): string {
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

function locatorLabel(locator: Record<string, unknown>): string {
  const number = (key: string) =>
    typeof locator[key] === "number" ? (locator[key] as number) : null;
  const start = number("start_seconds");
  const end = number("end_seconds");
  if (start !== null && end !== null) return `${timestamp(start)}–${timestamp(end)}`;
  if (number("image") !== null) return `Image ${number("image")}`;
  for (const [label, key] of [
    ["Pages", "page"],
    ["Slides", "slide"],
    ["Rows", "row"],
    ["Paragraphs", "paragraph"],
    ["Lines", "line"],
  ]) {
    const first = number(`${key}_start`) ?? number(key);
    const last = number(`${key}_end`) ?? first;
    if (first !== null)
      return `${typeof locator.sheet === "string" ? `Sheet ${locator.sheet}, ` : ""}${label} ${first}${last !== first ? `–${last}` : ""}`;
  }
  if (typeof locator.json_path === "string") return `JSON ${locator.json_path}`;
  if (number("chunk") !== null) return `Chunk ${number("chunk")}`;
  return "Source region";
}

function Grounding({ item }: { item: ApplicationKnowledgeDraft | GeneratedSkillDraft }) {
  return (
    <p className="muted">
      Evidence {item.evidence_ordinals.join(", ")} · {item.grounding_confidence} confidence
      {item.warnings.length ? ` · ${item.warnings.join("; ")}` : ""}
    </p>
  );
}

function KnowledgeItems({ items }: { items: ApplicationKnowledgeDraft[] }) {
  if (!items.length) return <p className="muted">No application knowledge found in this source.</p>;
  return items.map((item, index) => (
    <article className="panel" key={`${item.name}-${index}`}>
      <h3>{item.name}</h3>
      <p>{item.content}</p>
      <Grounding item={item} />
    </article>
  ));
}

function ArtifactItems({ items }: { items: ProcedureArtifactDraft[] }) {
  if (!items.length) return <p className="muted">No distinct procedures or artifacts found.</p>;
  return items.map((item, index) => (
    <article className="panel" key={`${item.name}-${index}`}>
      <p className="eyebrow">{item.kind}</p>
      <h3>{item.name}</h3>
      <p>{item.content}</p>
      {item.steps.length ? <ol>{item.steps.map((step, i) => <li key={i}>{step}</li>)}</ol> : null}
      <Grounding item={item} />
    </article>
  ));
}

function SkillItems({ items }: { items: GeneratedSkillDraft[] }) {
  if (!items.length) return <p className="muted">No testable Skills found in this source.</p>;
  return items.map((item, index) => (
    <article className="panel" key={`${item.name}-${index}`}>
      <h3>{item.name}</h3>
      <p>{item.definition.intent}</p>
      {([
        ["Preconditions", item.definition.preconditions],
        ["Inputs", item.definition.inputs],
        ["Constraints", item.definition.constraints],
        ["Expected outcomes", item.definition.expected_outcomes],
        ["Failure signals", item.definition.failure_signals],
      ] as const).map(([label, values]) =>
        values.length ? <p key={label}><strong>{label}:</strong> {values.join("; ")}</p> : null,
      )}
      <Grounding item={item} />
    </article>
  ));
}

export function KnowledgeResult({ preview }: { preview: KnowledgePreviewResponse }) {
  return (
    <div aria-live="polite">
      <p className="muted">Source: {preview.source.name} · {preview.source.processed_item_count} of {preview.source.source_item_count} source items processed.</p>
      <section className="section-block" aria-labelledby="knowledge-heading">
        <h2 id="knowledge-heading">Application knowledge</h2>
        <KnowledgeItems items={preview.application_knowledge} />
      </section>
      <section className="section-block" aria-labelledby="artifacts-heading">
        <h2 id="artifacts-heading">Artifacts</h2>
        <ArtifactItems items={preview.artifacts} />
      </section>
      <section className="section-block" aria-labelledby="skills-heading">
        <h2 id="skills-heading">Skills</h2>
        <SkillItems items={preview.skills} />
      </section>
      <section className="section-block" aria-labelledby="evidence-heading">
        <h2 id="evidence-heading">Evidence</h2>
        {preview.evidence.length ? preview.evidence.map((item) => (
          <div className="data-row" key={item.ordinal}>
            <span className="row-icon" aria-hidden="true"><FileText size={18} /></span>
            <span className="row-primary"><strong>Evidence {item.ordinal}</strong><span>{locatorLabel(item.source_locator)} · {item.evidence_type}</span></span>
          </div>
        )) : <p className="muted">No readable evidence was extracted.</p>}
      </section>
      {preview.extraction_issues.length ? (
        <section className="section-block" aria-labelledby="issues-heading">
          <h2 id="issues-heading">Extraction issues</h2>
          {preview.extraction_issues.map((issue, index) => (
            <p className="panel" key={`${issue.code}-${index}`}>
              <strong>{locatorLabel(issue.source_locator)}:</strong> {issue.message}
            </p>
          ))}
        </section>
      ) : null}
    </div>
  );
}

import { FileText } from "lucide-react";

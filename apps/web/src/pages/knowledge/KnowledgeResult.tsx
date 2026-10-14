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
    <div className="knowledge-grounding">
      <p className="muted">Source evidence: {item.evidence_ordinals.map((ordinal, index) => <span key={ordinal}>{index ? ", " : ""}<a href={`#evidence-${ordinal}`} onClick={() => document.getElementById(`evidence-${ordinal}`)?.setAttribute("open", "")}>Evidence {ordinal}</a></span>)}<span className="knowledge-confidence">Model confidence: {item.grounding_confidence}</span></p>
      {item.warnings.length ? <p className="knowledge-warning">{item.warnings.join("; ")}</p> : null}
    </div>
  );
}

function KnowledgeItems({ items }: { items: ApplicationKnowledgeDraft[] }) {
  if (!items.length) return <p className="muted">No application knowledge found in this source.</p>;
  return items.map((item, index) => (
    <article className="knowledge-item" key={`${item.name}-${index}`}>
      <h3>{item.name}</h3>
      <p>{item.content}</p>
      <Grounding item={item} />
    </article>
  ));
}

function ArtifactItems({ items }: { items: ProcedureArtifactDraft[] }) {
  if (!items.length) return <p className="muted">No distinct procedures or artifacts found.</p>;
  return items.map((item, index) => (
    <article className="knowledge-item" key={`${item.name}-${index}`}>
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
    <article className="knowledge-item" key={`${item.name}-${index}`}>
      <h3>{item.name}</h3>
      <p>{item.definition.intent}</p>
      <dl className="knowledge-skill-fields">{([
        ["Preconditions", item.definition.preconditions],
        ["Inputs", item.definition.inputs],
        ["Constraints", item.definition.constraints],
        ["Expected outcomes", item.definition.expected_outcomes],
        ["Failure signals", item.definition.failure_signals],
      ] as const).map(([label, values]) =>
        values.length ? <div key={label}><dt>{label}</dt><dd><ul>{values.map((value, i) => <li key={i}>{value}</li>)}</ul></dd></div> : null,
      )}</dl>
      <Grounding item={item} />
    </article>
  ));
}

export function KnowledgeResult({ preview }: { preview: KnowledgePreviewResponse }) {
  return (
    <div className="knowledge-result">
      <p className="knowledge-source-summary muted">{preview.source.processed_item_count} of {preview.source.source_item_count} source items processed.</p>
      <nav className="knowledge-contents" aria-label="Knowledge contents">
        <a href="#knowledge-heading">Knowledge <span>{preview.application_knowledge.length}</span></a>
        <a href="#artifacts-heading">Artifacts <span>{preview.artifacts.length}</span></a>
        <a href="#skills-heading">Skills <span>{preview.skills.length}</span></a>
        <a href="#evidence-heading">Evidence <span>{preview.evidence.length}</span></a>
        {preview.extraction_issues.length ? <a href="#issues-heading">Issues <span>{preview.extraction_issues.length}</span></a> : null}
      </nav>
      <section className={`section-block${preview.application_knowledge.length ? "" : " knowledge-empty-section"}`} aria-labelledby="knowledge-heading">
        <h2 id="knowledge-heading">Application knowledge</h2>
        {preview.application_knowledge.length ? <p className="knowledge-section-help">Facts, rules, and relationships learned from the source.</p> : null}
        <KnowledgeItems items={preview.application_knowledge} />
      </section>
      <section className={`section-block${preview.artifacts.length ? "" : " knowledge-empty-section"}`} aria-labelledby="artifacts-heading">
        <h2 id="artifacts-heading">Artifacts</h2>
        {preview.artifacts.length ? <p className="knowledge-section-help">Reusable procedures or structured instructions from the source.</p> : null}
        <ArtifactItems items={preview.artifacts} />
      </section>
      <section className={`section-block${preview.skills.length ? "" : " knowledge-empty-section"}`} aria-labelledby="skills-heading">
        <h2 id="skills-heading">Skills</h2>
        {preview.skills.length ? <p className="knowledge-section-help">Capabilities agents can test, with conditions and expected outcomes.</p> : null}
        <SkillItems items={preview.skills} />
      </section>
      <section className="section-block" aria-labelledby="evidence-heading">
        <h2 id="evidence-heading">Evidence</h2>
        {preview.evidence.length ? <p className="knowledge-section-help">Open a source region to check the grounding of generated items.</p> : null}
        {preview.evidence.length ? preview.evidence.map((item) => (
          <details className="knowledge-evidence" id={`evidence-${item.ordinal}`} key={item.ordinal}>
            <summary><span className="row-primary"><strong>Evidence {item.ordinal}</strong><span>{locatorLabel(item.source_locator)} · {item.evidence_type}</span></span></summary>
            {item.content_text ? <div className="knowledge-evidence-content" tabIndex={0}>{item.content_text}</div> : item.content_json ? <pre className="knowledge-evidence-content" tabIndex={0}>{JSON.stringify(item.content_json, null, 2)}</pre> : <p className="muted knowledge-evidence-content">This evidence is a media region. Open the original source to review it.</p>}
          </details>
        )) : <p className="muted">No readable evidence was extracted.</p>}
      </section>
      {preview.extraction_issues.length ? (
        <section className="section-block" aria-labelledby="issues-heading">
          <h2 id="issues-heading">Extraction issues</h2>
          {preview.extraction_issues.map((issue, index) => (
            <p className="knowledge-item knowledge-warning" key={`${issue.code}-${index}`}>
              <strong>{locatorLabel(issue.source_locator)}:</strong> {issue.message}
            </p>
          ))}
        </section>
      ) : null}
    </div>
  );
}

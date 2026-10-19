import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import {
  type ApplicationKnowledgeDraft,
  type GeneratedSkillDraft,
  type KnowledgePreviewResponse,
  type ProcedureArtifactDraft,
} from "../../lib/api";

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
    if (first !== null) {
      return `${typeof locator.sheet === "string" ? `Sheet ${locator.sheet}, ` : ""}${label} ${first}${
        last !== first ? `–${last}` : ""
      }`;
    }
  }
  if (typeof locator.json_path === "string") return `JSON ${locator.json_path}`;
  if (number("chunk") !== null) return `Chunk ${number("chunk")}`;
  return "Source region";
}

function CollapsibleSnippet({ content, threshold = 320 }: { content: string; threshold?: number }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = content.length > threshold;

  return (
    <div className="collapsible-snippet" style={{ margin: "6px 0" }}>
      <p
        style={
          !expanded && isLong
            ? {
                display: "-webkit-box",
                WebkitLineClamp: 4,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                whiteSpace: "pre-wrap",
                margin: 0,
              }
            : { whiteSpace: "pre-wrap", margin: 0 }
        }
      >
        {content}
      </p>
      {isLong ? (
        <button
          type="button"
          className="text-link"
          onClick={() => setExpanded((prev) => !prev)}
          aria-expanded={expanded}
          style={{
            background: "none",
            border: "none",
            padding: "4px 0",
            marginTop: "4px",
            cursor: "pointer",
            fontSize: "12px",
            fontWeight: 600,
            color: "var(--primary)",
          }}
        >
          {expanded ? "Show less" : `Show full text (${content.length} characters)`}
        </button>
      ) : null}
    </div>
  );
}

function Grounding({ item }: { item: ApplicationKnowledgeDraft | GeneratedSkillDraft }) {
  return (
    <div
      className="knowledge-grounding"
      style={{
        marginTop: "12px",
        paddingTop: "8px",
        borderTop: "1px dashed var(--border)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          <span className="muted" style={{ fontSize: "12px" }}>Source evidence:</span>
          {item.evidence_ordinals.length ? (
            item.evidence_ordinals.map((ordinal) => (
              <a
                key={ordinal}
                href={`#evidence-${ordinal}`}
                className="evidence-marker"
                onClick={() => document.getElementById(`evidence-${ordinal}`)?.setAttribute("open", "")}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                  padding: "2px 8px",
                  background: "var(--surface-muted)",
                  border: "1px solid var(--border)",
                  borderRadius: "4px",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "var(--primary)",
                  textDecoration: "none",
                }}
              >
                <span style={{ fontFamily: "monospace", color: "var(--text-3)", fontSize: "11px" }}>#{ordinal}</span>
                <span>Evidence {ordinal}</span>
              </a>
            ))
          ) : (
            <span className="muted" style={{ fontSize: "12px" }}>None cited</span>
          )}
        </div>
        <span className="knowledge-confidence muted" style={{ fontSize: "12px" }}>
          Model confidence: <strong style={{ color: "var(--text)" }}>{item.grounding_confidence}</strong>
        </span>
      </div>
      {item.warnings.length ? (
        <p className="knowledge-warning" style={{ marginTop: "6px", fontSize: "12px" }}>
          {item.warnings.join("; ")}
        </p>
      ) : null}
    </div>
  );
}

function KnowledgeItems({ items }: { items: ApplicationKnowledgeDraft[] }) {
  if (!items.length) return <p className="muted">No application knowledge found in this source.</p>;
  return items.map((item, index) => (
    <article className="knowledge-item" key={`${item.name}-${index}`}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "4px" }}>
        <span className="status-badge status-neutral" style={{ fontSize: "11px", padding: "1px 7px" }}>
          Generated summary
        </span>
      </div>
      <h3>{item.name}</h3>
      <CollapsibleSnippet content={item.content} />
      <Grounding item={item} />
    </article>
  ));
}

function ArtifactItems({ items }: { items: ProcedureArtifactDraft[] }) {
  if (!items.length) return <p className="muted">No distinct procedures or artifacts found.</p>;
  return items.map((item, index) => (
    <article className="knowledge-item" key={`${item.name}-${index}`}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "4px" }}>
        <p className="eyebrow" style={{ margin: 0 }}>{item.kind}</p>
        <span className="status-badge status-neutral" style={{ fontSize: "11px", padding: "1px 7px" }}>
          Generated summary
        </span>
      </div>
      <h3>{item.name}</h3>
      <CollapsibleSnippet content={item.content} />
      {item.steps.length ? (
        <ol style={{ margin: "10px 0", paddingLeft: "20px" }}>
          {item.steps.map((step, i) => (
            <li key={i} style={{ margin: "4px 0" }}>{step}</li>
          ))}
        </ol>
      ) : null}
      <Grounding item={item} />
    </article>
  ));
}

function SkillItems({ items }: { items: GeneratedSkillDraft[] }) {
  if (!items.length) return <p className="muted">No testable Skills found in this source.</p>;
  return items.map((item, index) => (
    <article className="knowledge-item" key={`${item.name}-${index}`}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "4px" }}>
        <span className="status-badge status-neutral" style={{ fontSize: "11px", padding: "1px 7px" }}>
          Generated summary
        </span>
      </div>
      <h3>{item.name}</h3>
      <CollapsibleSnippet content={item.definition.intent} />
      <dl className="knowledge-skill-fields">
        {([
          ["Preconditions", item.definition.preconditions],
          ["Inputs", item.definition.inputs],
          ["Constraints", item.definition.constraints],
          ["Expected outcomes", item.definition.expected_outcomes],
          ["Failure signals", item.definition.failure_signals],
        ] as const).map(([label, values]) =>
          values.length ? (
            <div key={label}>
              <dt>{label}</dt>
              <dd>
                <ul>
                  {values.map((value, i) => (
                    <li key={i}>{value}</li>
                  ))}
                </ul>
              </dd>
            </div>
          ) : null,
        )}
      </dl>
      <Grounding item={item} />
    </article>
  ));
}

export function KnowledgeResult({ preview }: { preview: KnowledgePreviewResponse }) {
  return (
    <div className="knowledge-result">
      <p className="knowledge-source-summary muted">
        {preview.source.processed_item_count} of {preview.source.source_item_count} source items processed.
      </p>
      <nav className="knowledge-contents" aria-label="Knowledge contents">
        <a href="#knowledge-heading">
          Knowledge <span>{preview.application_knowledge.length}</span>
        </a>
        <a href="#artifacts-heading">
          Artifacts <span>{preview.artifacts.length}</span>
        </a>
        <a href="#skills-heading">
          Skills <span>{preview.skills.length}</span>
        </a>
        <a href="#evidence-heading">
          Evidence <span>{preview.evidence.length}</span>
        </a>
        {preview.extraction_issues.length ? (
          <a href="#issues-heading">
            Issues <span>{preview.extraction_issues.length}</span>
          </a>
        ) : null}
      </nav>

      <section
        className={`section-block${preview.application_knowledge.length ? "" : " knowledge-empty-section"}`}
        aria-labelledby="knowledge-heading"
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 id="knowledge-heading">Application knowledge</h2>
          <span className="status-badge status-neutral" style={{ fontSize: "11px" }}>
            {preview.application_knowledge.length} {preview.application_knowledge.length === 1 ? "item" : "items"}
          </span>
        </div>
        {preview.application_knowledge.length ? (
          <p className="knowledge-section-help">Facts, rules, and relationships learned from the source.</p>
        ) : null}
        <KnowledgeItems items={preview.application_knowledge} />
      </section>

      <section
        className={`section-block${preview.artifacts.length ? "" : " knowledge-empty-section"}`}
        aria-labelledby="artifacts-heading"
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 id="artifacts-heading">Artifacts</h2>
          <span className="status-badge status-neutral" style={{ fontSize: "11px" }}>
            {preview.artifacts.length} {preview.artifacts.length === 1 ? "item" : "items"}
          </span>
        </div>
        {preview.artifacts.length ? (
          <p className="knowledge-section-help">Reusable procedures or structured instructions from the source.</p>
        ) : null}
        <ArtifactItems items={preview.artifacts} />
      </section>

      <section
        className={`section-block${preview.skills.length ? "" : " knowledge-empty-section"}`}
        aria-labelledby="skills-heading"
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 id="skills-heading">Skills</h2>
          <span className="status-badge status-neutral" style={{ fontSize: "11px" }}>
            {preview.skills.length} {preview.skills.length === 1 ? "skill" : "skills"}
          </span>
        </div>
        {preview.skills.length ? (
          <p className="knowledge-section-help">Capabilities agents can test, with conditions and expected outcomes.</p>
        ) : null}
        <SkillItems items={preview.skills} />
      </section>

      <section className="section-block" aria-labelledby="evidence-heading">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 id="evidence-heading">Evidence</h2>
          <span className="status-badge status-info" style={{ fontSize: "11px" }}>
            {preview.evidence.length} {preview.evidence.length === 1 ? "source region" : "source regions"}
          </span>
        </div>
        {preview.evidence.length ? (
          <p className="knowledge-section-help">Open a source region to check the grounding of generated items against original source evidence.</p>
        ) : null}
        {preview.evidence.length ? (
          preview.evidence.map((item) => (
            <details className="knowledge-evidence" id={`evidence-${item.ordinal}`} key={item.ordinal}>
              <summary>
                <span className="row-primary">
                  <strong>Evidence {item.ordinal}</strong>
                  <span>
                    {locatorLabel(item.source_locator)} · {item.evidence_type}
                  </span>
                </span>
              </summary>
              <div style={{ padding: "8px 0" }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: "8px",
                    fontSize: "12px",
                  }}
                >
                  <span className="status-badge status-info" style={{ fontSize: "11px", padding: "1px 6px" }}>
                    Source evidence
                  </span>
                  <span className="monospace" style={{ color: "var(--text-3)", fontSize: "11px" }}>
                    Extractor: {item.extractor_name} v{item.extractor_version}
                  </span>
                </div>
                {item.content_text ? (
                  <div className="knowledge-evidence-content" tabIndex={0}>
                    <CollapsibleSnippet content={item.content_text} threshold={400} />
                  </div>
                ) : item.content_json ? (
                  <pre className="knowledge-evidence-content" tabIndex={0}>
                    {JSON.stringify(item.content_json, null, 2)}
                  </pre>
                ) : (
                  <p className="muted knowledge-evidence-content">
                    This evidence is a media region. Open the original source to review it.
                  </p>
                )}
              </div>
            </details>
          ))
        ) : (
          <p className="muted">No readable evidence was extracted.</p>
        )}
      </section>

      {preview.extraction_issues.length ? (
        <section className="section-block" aria-labelledby="issues-heading">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <h2 id="issues-heading">Extraction issues</h2>
            <span className="status-badge status-warning" style={{ fontSize: "11px" }}>
              {preview.extraction_issues.length} {preview.extraction_issues.length === 1 ? "issue" : "issues"}
            </span>
          </div>
          <p className="knowledge-section-help">
            The model recorded these issues while processing the source. Review them to verify whether any critical content was omitted.
          </p>
          {preview.extraction_issues.map((issue, index) => (
            <div
              className="knowledge-item knowledge-warning"
              key={`${issue.code}-${index}`}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "10px",
                padding: "12px 16px",
                margin: "8px 0",
                borderRadius: "6px",
                background: "var(--warning-bg)",
                border: "1px solid var(--warning-border)",
              }}
            >
              <AlertTriangle size={18} style={{ color: "var(--warning)", flexShrink: 0, marginTop: "2px" }} />
              <div>
                <p style={{ margin: 0 }}>
                  <strong>{locatorLabel(issue.source_locator)}:</strong> {issue.message}
                </p>
                <span className="monospace" style={{ fontSize: "11px", color: "var(--text-3)", display: "block", marginTop: "4px" }}>
                  Issue code: {issue.code}
                </span>
              </div>
            </div>
          ))}
        </section>
      ) : null}
    </div>
  );
}

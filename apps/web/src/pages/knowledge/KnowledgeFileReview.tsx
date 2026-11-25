import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../components/ui/button";
import { InlineAlert } from "../../components/ui/Feedback";
import { LoadingPanel } from "../../components/ui/StateViews";
import { api, type KnowledgeFileIndex, type KnowledgePreviewEvidence } from "../../lib/api";

// The .md files are generated in one constrained format (doc 33 §3.4):
// frontmatter, # / ## headings, paragraphs, - / 1. lists, > exception
// quotes, **bold**, `code`, and "Evidence N" references. This renderer
// covers exactly that format and nothing more; everything renders as
// React text, never as injected HTML.

function timestamp(seconds: number): string {
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

// Re-implemented from KnowledgeResult.tsx against the evidence.json unit
// shape (doc 33 §3.5): the same locator labels the legacy preview used.
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

function EvidenceChip({ ordinal }: { ordinal: string }) {
  return (
    <a
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
      <span aria-hidden="true" style={{ fontFamily: "var(--font-mono)", color: "var(--text-3)", fontSize: "11px" }}>#{ordinal}</span>
      <span>Evidence {ordinal}</span>
    </a>
  );
}

function renderEvidenceLinks(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(Evidence\s+\d+)/g).map((part, i) => {
    const match = /^Evidence\s+(\d+)$/.exec(part);
    if (!match) return <span key={`${keyPrefix}-t${i}`}>{part}</span>;
    return <EvidenceChip key={`${keyPrefix}-e${i}`} ordinal={match[1]} />;
  });
}

const INLINE_TOKEN = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(INLINE_TOKEN).filter(Boolean).map((part, i) => {
    const key = `${keyPrefix}-${i}`;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={key}>{renderEvidenceLinks(part.slice(2, -2), key)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={key}>{part.slice(1, -1)}</code>;
    }
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(part);
    if (link) {
      return (
        <a key={key} href={link[2]} target="_blank" rel="noreferrer">
          {link[1]}
        </a>
      );
    }
    return <span key={key}>{renderEvidenceLinks(part, key)}</span>;
  });
}

type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "quote"; text: string };

function stripFrontmatter(markdown: string): string {
  if (!markdown.startsWith("---")) return markdown;
  const lines = markdown.split("\n");
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === "---" || lines[i].trim() === "...") {
      return lines.slice(i + 1).join("\n");
    }
  }
  return markdown;
}

function parseBlocks(markdown: string): Block[] {
  const blocks: Block[] = [];
  let para: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let quote: string[] = [];
  const flushPara = () => {
    if (para.length) blocks.push({ kind: "paragraph", text: para.join(" ") });
    para = [];
  };
  const flushList = () => {
    if (list) blocks.push({ kind: list.ordered ? "ol" : "ul", items: list.items });
    list = null;
  };
  const flushQuote = () => {
    if (quote.length) blocks.push({ kind: "quote", text: quote.join(" ") });
    quote = [];
  };
  const flushAll = () => {
    flushPara();
    flushList();
    flushQuote();
  };
  for (const raw of markdown.split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim() || line.trim() === "---") {
      flushAll();
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      flushAll();
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
      continue;
    }
    const unordered = /^[-*]\s+(.*)$/.exec(line);
    if (unordered) {
      flushPara();
      flushQuote();
      if (!list || list.ordered) {
        flushList();
        list = { ordered: false, items: [] };
      }
      list.items.push(unordered[1]);
      continue;
    }
    const ordered = /^\d+\.\s+(.*)$/.exec(line);
    if (ordered) {
      flushPara();
      flushQuote();
      if (!list || !list.ordered) {
        flushList();
        list = { ordered: true, items: [] };
      }
      list.items.push(ordered[1]);
      continue;
    }
    const quoted = /^>\s?(.*)$/.exec(line);
    if (quoted) {
      flushPara();
      flushList();
      quote.push(quoted[1]);
      continue;
    }
    flushList();
    flushQuote();
    para.push(line.trim());
  }
  flushAll();
  return blocks;
}

export function MarkdownView({ markdown }: { markdown: string }) {
  const blocks = parseBlocks(stripFrontmatter(markdown));
  return (
    <div className="knowledge-file-markdown">
      {blocks.map((block, i) => {
        const key = `b${i}`;
        switch (block.kind) {
          case "heading": {
            const text = renderInline(block.text, key);
            if (block.level <= 1) return <h2 key={key}>{text}</h2>;
            if (block.level === 2) return <h3 key={key}>{text}</h3>;
            return <h4 key={key}>{text}</h4>;
          }
          case "ul":
            return (
              <ul key={key}>
                {block.items.map((item, j) => (
                  <li key={j}>{renderInline(item, `${key}-${j}`)}</li>
                ))}
              </ul>
            );
          case "ol":
            return (
              <ol key={key}>
                {block.items.map((item, j) => (
                  <li key={j}>{renderInline(item, `${key}-${j}`)}</li>
                ))}
              </ol>
            );
          case "quote":
            return <blockquote key={key}>{renderInline(block.text, key)}</blockquote>;
          default:
            return <p key={key}>{renderInline(block.text, key)}</p>;
        }
      })}
    </div>
  );
}

function CollapsibleText({ content, threshold = 400 }: { content: string; threshold?: number }) {
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

function FileEvidence({ evidence }: { evidence: KnowledgePreviewEvidence[] }) {
  if (!evidence.length) return null;
  return (
    <section className="section-block" aria-labelledby="file-evidence-heading">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h3 id="file-evidence-heading">Evidence</h3>
        <span className="knowledge-meta" style={{ fontSize: "11px" }}>
          {evidence.length} {evidence.length === 1 ? "source region" : "source regions"}
        </span>
      </div>
      <p className="knowledge-section-help">Open a source region to check this file against the original source evidence.</p>
      {evidence.map((item) => (
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
              <span className="knowledge-meta" style={{ fontSize: "11px", padding: "1px 6px" }}>
                Source evidence
              </span>
              <span className="monospace" style={{ color: "var(--text-3)", fontSize: "11px" }}>
                Extractor: {item.extractor_name} v{item.extractor_version}
              </span>
            </div>
            {item.content_text ? (
              <div className="knowledge-evidence-content" tabIndex={0}>
                <CollapsibleText content={item.content_text} />
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
      ))}
    </section>
  );
}

export function KnowledgeFileReview({
  workspaceId,
  entryId,
  files,
}: {
  workspaceId: string;
  entryId: string;
  files: KnowledgeFileIndex[];
}) {
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const selected = files.find((file) => file.slug === selectedSlug) ?? files[0];

  const content = useQuery({
    queryKey: ["knowledge-file", workspaceId, entryId, selected?.slug],
    queryFn: () => api.getKnowledgeFile(workspaceId, entryId, selected.slug),
    enabled: Boolean(selected),
  });

  return (
    <div
      className="knowledge-file-review"
      style={{ display: "grid", gridTemplateColumns: "minmax(220px, 280px) 1fr", gap: "20px", alignItems: "start" }}
    >
      <nav className="knowledge-file-list" aria-label="Knowledge files" style={{ display: "grid", gap: "8px" }}>
        {files.map((file) => {
          const active = selected !== undefined && file.slug === selected.slug;
          return (
            <button
              key={file.slug}
              type="button"
              aria-current={active ? "true" : undefined}
              onClick={() => setSelectedSlug(file.slug)}
              style={{
                textAlign: "left",
                display: "grid",
                gap: "4px",
                padding: "12px",
                borderRadius: "8px",
                cursor: "pointer",
                border: `1px solid ${active ? "var(--primary)" : "var(--border)"}`,
                background: active ? "var(--surface-muted)" : "var(--surface)",
                color: "var(--text)",
              }}
            >
              <strong style={{ fontSize: "14px" }}>{file.title}</strong>
              <span style={{ fontSize: "12px", color: "var(--text-2)" }}>{file.description}</span>
              <span className="knowledge-meta" style={{ fontSize: "11px" }}>
                {file.token_count} tokens · v{file.version}
                {file.status === "superseded" ? " · Superseded" : ""}
              </span>
            </button>
          );
        })}
      </nav>
      <div className="knowledge-file-pane">
        {content.isPending ? (
          <LoadingPanel label="Loading file" />
        ) : content.isError || !content.data ? (
          <InlineAlert
            severity="error"
            title="Could not load this file"
            role="alert"
            action={
              <Button variant="ghost" size="sm" onClick={() => void content.refetch()}>
                Try again
              </Button>
            }
          >
            {content.error?.message || "The file could not be loaded."}
          </InlineAlert>
        ) : (
          <article>
            <MarkdownView markdown={content.data.markdown} />
            <FileEvidence evidence={content.data.evidence} />
          </article>
        )}
      </div>
    </div>
  );
}

import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, X } from "lucide-react";
import { filterNavCommands, runCommand, type NavCommand } from "../../lib/navCommands";

/* Command palette (Phase 2c, Spec 2 §2): ONE registry
   (lib/navCommands — the same list that renders the shell nav)
   and ONE runCommand() path for Enter and click alike.
   APG combobox model: the input keeps focus, selection is virtual
   via aria-activedescendant, arrows move the highlight across
   groups, Enter runs and closes, Esc closes and returns focus
   (Radix Dialog), the query is discarded on close. */

export function CommandMenu({
  triggerVariant = "default",
}: {
  triggerVariant?: "default" | "field";
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const items = useMemo(() => filterNavCommands(query), [query]);
  useEffect(() => { setActiveIndex(0); }, [query]);

  const select = (command: NavCommand) => {
    runCommand(navigate, command);
    setOpen(false);
  };

  const onInputKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((i) => (items.length ? (i + 1) % items.length : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((i) => (items.length ? (i - 1 + items.length) % items.length : 0));
    } else if (event.key === "Home") {
      event.preventDefault();
      setActiveIndex(0);
    } else if (event.key === "End") {
      event.preventDefault();
      setActiveIndex(Math.max(0, items.length - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (items[activeIndex]) select(items[activeIndex]);
    }
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(value) => {
        setOpen(value);
        if (!value) setQuery("");
      }}
    >
      <Dialog.Trigger asChild>
        {triggerVariant === "field" ? (
          <button className="search-trigger search-trigger--field" aria-label="Search pages">
            <Search size={16} aria-hidden="true" />
            <span>Search…</span>
            <kbd className="kbd">⌘K</kbd>
          </button>
        ) : (
          <button className="search-trigger" aria-label="Open quick navigation">
            <Search size={16} aria-hidden="true" />
            <span>Go to…</span>
            <kbd className="kbd">⌘K</kbd>
          </button>
        )}
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="mt-dialog command-dialog"
          aria-label="Quick navigation"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            inputRef.current?.focus();
          }}
        >
          <Dialog.Title className="visually-hidden">Quick navigation</Dialog.Title>
          <Dialog.Description className="visually-hidden">
            Find a workspace page. Use the arrow keys to choose a result, Enter to open it.
          </Dialog.Description>
          <div className="command-input-row">
            <Search size={16} aria-hidden="true" />
            <label className="visually-hidden" htmlFor="command-query">Search pages</label>
            <input
              ref={inputRef}
              id="command-query"
              role="combobox"
              aria-expanded={items.length > 0}
              aria-controls="command-results"
              aria-activedescendant={items[activeIndex] ? `command-option-${items[activeIndex].id}` : undefined}
              placeholder="Type a command or search…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={onInputKeyDown}
              autoComplete="off"
            />
            <Dialog.Close className="mt-dialog-close" aria-label="Close quick navigation" style={{ position: "static" }}>
              <X size={16} aria-hidden="true" />
            </Dialog.Close>
          </div>
          <div className="command-results" role="listbox" id="command-results" aria-label="Navigation results">
            {items.length ? <p className="command-group-label" role="presentation">Go to</p> : null}
            {items.map((item, index) => (
              <div
                key={item.id}
                id={`command-option-${item.id}`}
                role="option"
                aria-selected={index === activeIndex}
                data-active={index === activeIndex}
                className="command-row"
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => select(item)}
              >
                <span>{item.title}</span>
                <small>{item.description}</small>
              </div>
            ))}
            {items.length === 0 ? (
              <div className="command-empty">
                <strong>No results for “{query}”</strong>
                <span>Try a different word, or browse from Home.</span>
              </div>
            ) : null}
          </div>
          <p className="visually-hidden" role="status" aria-live="polite">
            {items.length} {items.length === 1 ? "result" : "results"}
          </p>
          <div className="command-footer" aria-hidden="true">
            <span>↑↓ Navigate</span>
            <span>↵ Select</span>
            <span>Esc Close</span>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

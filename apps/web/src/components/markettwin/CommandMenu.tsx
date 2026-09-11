import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Search, X, ArrowUpRight } from "lucide-react";
import { Input } from "../ui/input";

const destinations = [
  { title: "Workspace overview", description: "Applications and test activity", href: "/overview" },
  { title: "Applications", description: "Choose a product or start a test", href: "/applications" },
  { title: "Tests", description: "Find a test and inspect its results", href: "/runs" },
  { title: "Profile settings", description: "Your account and workspace", href: "/settings/profile" },
];

export function CommandMenu() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(value => !value);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const items = destinations.filter(item => `${item.title} ${item.description}`.toLowerCase().includes(query.toLowerCase()));

  return <Dialog.Root open={open} onOpenChange={value => { setOpen(value); setQuery(""); }}>
    <Dialog.Trigger asChild><button className="search-trigger" aria-label="Open quick navigation"><Search size={16} aria-hidden="true" /><span>Go to…</span><kbd>Ctrl/⌘ K</kbd></button></Dialog.Trigger>
    <Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="command-dialog" onOpenAutoFocus={event => { event.preventDefault(); inputRef.current?.focus(); }}>
      <div className="dialog-heading"><Dialog.Title>Quick navigation</Dialog.Title><Dialog.Close className="icon-button" aria-label="Close quick navigation"><X size={20} aria-hidden="true" /></Dialog.Close></div>
      <Dialog.Description className="muted">Find a workspace page. Use Tab to choose a result.</Dialog.Description>
      <label className="visually-hidden" htmlFor="command-query">Search pages</label>
      <Input ref={inputRef} id="command-query" placeholder="Search pages…" value={query} onChange={event => setQuery(event.target.value)} autoComplete="off" />
      <nav className="command-results" aria-label="Navigation results">{items.map(item => <Link to={item.href} key={item.href} onClick={() => setOpen(false)}><span><strong>{item.title}</strong><small>{item.description}</small></span><ArrowUpRight size={17} aria-hidden="true" /></Link>)}</nav>
      {items.length === 0 ? <p role="status">No matching pages. Try “tests” or “applications”.</p> : null}
    </Dialog.Content></Dialog.Portal>
  </Dialog.Root>;
}

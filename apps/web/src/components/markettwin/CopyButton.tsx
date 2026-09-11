import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "../ui/button";

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [state, setState] = useState<"idle" | "copied" | "error">("idle");
  async function copy() {
    try { await navigator.clipboard.writeText(text); setState("copied"); }
    catch { setState("error"); }
  }
  return <span className="copy-control"><Button variant="secondary" size="sm" onClick={() => void copy()}>
    {state === "copied" ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
    {state === "copied" ? "Copied" : label}
  </Button><span className={state === "error" ? "form-error" : "visually-hidden"} role="status">
    {state === "error" ? "Copy unavailable. Select and copy the text directly." : state === "copied" ? "Copied to clipboard." : ""}
  </span></span>;
}

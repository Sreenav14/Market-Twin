import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { LucideProvider } from "lucide-react";
import { queryClient } from "./lib/query";
import "@fontsource/ibm-plex-mono/latin-400.css";

import { App } from "./app/App";
import { RenderErrorBoundary } from "./app/RenderErrorBoundary";
import "./styles.css";
import { applyTheme, getStoredTheme } from "./lib/theme";

applyTheme(getStoredTheme());
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (getStoredTheme() === "system") applyTheme("system");
});
window.addEventListener("storage", (event) => {
  if (event.key === "markettwin-theme") applyTheme(getStoredTheme());
});

const rootElement = document.getElementById("root");

if (rootElement === null) {
  throw new Error("MarketTwin root element was not found.");
}

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <LucideProvider strokeWidth={1.7}>
        <RenderErrorBoundary><App /></RenderErrorBoundary>
      </LucideProvider>
    </QueryClientProvider>
  </StrictMode>,
);

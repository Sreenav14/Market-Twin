import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

// jsdom does not implement the media-query API used by the theme preference.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Concurrent Chromium/backend checks can delay React transitions on development
// machines; keep asserting completion, with time for the scheduled render.
configure({ asyncUtilTimeout: 5000 });

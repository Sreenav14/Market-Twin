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

// Phase 2c: Radix popper surfaces (Menu/Popover/Tooltip) use
// ResizeObserver and pointer capture, which jsdom does not
// implement. Inert stubs — layout is not asserted in jsdom.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
Object.defineProperty(window, "ResizeObserver", { writable: true, value: ResizeObserverStub });
if (!HTMLElement.prototype.hasPointerCapture) {
  HTMLElement.prototype.hasPointerCapture = () => false;
  HTMLElement.prototype.releasePointerCapture = () => {};
  HTMLElement.prototype.setPointerCapture = () => {};
}
if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

// Concurrent Chromium/backend checks can delay React transitions on development
// machines; keep asserting completion, with time for the scheduled render.
configure({ asyncUtilTimeout: 5000 });

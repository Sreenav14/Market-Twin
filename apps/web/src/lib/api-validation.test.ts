import { afterEach, expect, it, vi } from "vitest";
import { request } from "./api";

afterEach(() => vi.unstubAllGlobals());

it("shows field validation messages without echoing the submitted input", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [
    { loc: ["body", "study_brief"], msg: "String should have at least 10 characters", input: "private content" },
  ] }), { status: 422 })));
  await expect(request("/fixture")).rejects.toThrow("study_brief: String should have at least 10 characters");
});

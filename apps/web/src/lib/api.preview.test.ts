import { afterEach, expect, it, vi } from "vitest";

import { api } from "./api";

afterEach(() => vi.unstubAllGlobals());

it("sends workspace ingestion as browser-encoded multipart data", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ source: { name: "source.txt" } }), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const file = new File(["source"], "source.txt", { type: "text/plain" });

  await api.ingestKnowledge("workspace", file, "Source knowledge", ["product_knowledge"]);

  const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(path).toBe("/api/v1/workspaces/workspace/ingestion");
  expect(init.credentials).toBe("include");
  expect(init.headers).toBeUndefined();
  expect(init.body).toBeInstanceOf(FormData);
  expect((init.body as FormData).get("file")).toBe(file);
  expect((init.body as FormData).get("name")).toBe("Source knowledge");
  expect((init.body as FormData).getAll("roles")).toEqual(["product_knowledge"]);
});

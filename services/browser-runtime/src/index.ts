import { runPublicPage } from "./browser/run-public-page.js";
import type { PublicPageRunRequest } from "./browser/types.js";

async function main(): Promise<void> {
  const request: PublicPageRunRequest = {
    runId: "example-run",
    url: "https://example.com",
    allowedDomains: ["example.com"],
    timeoutMs: 30_000,
  };

  const result = await runPublicPage(request)

  console.log(JSON.stringify(result, null, 2));
}

main().catch((error: unknown) => {
  const message =
    error instanceof Error
      ? error.message
      : "Unknown browser runtime error";

  console.error(message);
  process.exitCode = 1;
});
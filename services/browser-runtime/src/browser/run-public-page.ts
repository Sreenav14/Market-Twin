import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { validateTargetUrl } from "../security/validate-url.js";
import { chromium } from "playwright";
import { resolveAndValidatePublicHost } from "../security/resolve-host.js";

import type {
  FailedRequest,
  PublicPageRunRequest,
  PublicPageRunResult,
} from "./types.js";

export async function runPublicPage(request: PublicPageRunRequest): Promise<PublicPageRunResult> {
    
  
  const validatedUrl = validateTargetUrl(
    request.url,
    request.allowedDomains,
  );

  await resolveAndValidatePublicHost(
    validatedUrl.hostname,
  );

  const artifactDirectory = resolve(
    "artifacts",
    "runs",
    request.runId,
  );


  await mkdir(artifactDirectory, {
    recursive: true,
  });


  const screenshotPath = resolve(
    artifactDirectory,
    "screenshot.png",
  );

  const tracePath = resolve(
    artifactDirectory,
    "trace.zip",
  );

  const accessibilitySnapshotPath = resolve(
    artifactDirectory,
    "accessibility.yml",
  );

  const consoleErrorsPath = resolve(
    artifactDirectory,
    "console-errors.json",
  );

  const pageErrorsPath = resolve(
    artifactDirectory,
    "page-errors.json",
  );

  const failedRequestsPath = resolve(
    artifactDirectory,
    "failed-requests.json",
  );

  const browser = await chromium.launch({
    headless: true,
  });

  try {
    const context = await browser.newContext();

    await context.tracing.start({
      screenshots: true,
      snapshots: true,
      sources: true,
    });

    try {
      const page = await context.newPage();

      const consoleErrors: string[] = [];
      const pageErrors: string[] = [];
      const failedRequests: FailedRequest[] = [];

      page.on("console", (message) => {
        if (message.type() === "error") {
          consoleErrors.push(message.text());
        }
      });

      page.on("pageerror", (error) => {
        pageErrors.push(error.message);
      });

      page.on("requestfailed", (request) => {
        failedRequests.push({
          url: request.url(),
          method: request.method(),
          resourceType: request.resourceType(),
          errorText:
            request.failure()?.errorText ??
            "Unknown network error",
        });
      });

      await page.goto(validatedUrl.href, {
        waitUntil: "domcontentloaded",
        timeout: request.timeoutMs,
      });

      await page.screenshot({
        path: screenshotPath,
        fullPage: true,
      });

      const accessibilitySnapshot =
        await page.ariaSnapshot();

      await writeFile(
        accessibilitySnapshotPath,
        accessibilitySnapshot,
        "utf8",
      );

      await writeFile(
        consoleErrorsPath,
        JSON.stringify(consoleErrors, null, 2),
        "utf8",
      );

      await writeFile(
        pageErrorsPath,
        JSON.stringify(pageErrors, null, 2),
        "utf8",
      );

      await writeFile(
        failedRequestsPath,
        JSON.stringify(failedRequests, null, 2),
        "utf8",
      );

      return {
        runId: request.runId,
        requestedUrl: request.url,
        status: "completed",
        title: await page.title(),
        finalUrl: page.url(),
        screenshotPath,
        tracePath,
        accessibilitySnapshotPath,
        consoleErrors,
        consoleErrorsPath,
        pageErrors,
        pageErrorsPath,
        failedRequests,
        failedRequestsPath,
      };
    } finally {
      await context.tracing.stop({
        path: tracePath,
      });

      await context.close();
    }
  } finally {
    await browser.close();
  }
}
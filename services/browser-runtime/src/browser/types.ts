export interface FailedRequest {
    url: string;
    method: string;
    resourceType: string;
    errorText: string;
}

export interface PublicPageRunRequest {
    runId: string;
    url: string;
    allowedDomains: string[];
    timeoutMs: number;
  }

export interface PublicPageRunResult {
    status: "completed";
    runId: string;
    requestedUrl: string;
    finalUrl: string;
    title: string;
    screenshotPath: string;
    tracePath: string;
    accessibilitySnapshotPath: string;
    consoleErrors: string[];
    consoleErrorsPath: string;
    pageErrors: string[];
    pageErrorsPath: string;
    failedRequests: FailedRequest[];
    failedRequestsPath: string;
}
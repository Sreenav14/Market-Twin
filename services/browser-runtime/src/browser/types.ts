export interface AllowedOrigin {
  scheme: "http" | "https";
  hostname: string;
  port: number | null;
  include_subdomains: boolean;
}

export type NetworkPolicy =
  | "public_only"
  | "local_development";

export interface FailedRequest {
  url: string;
  method: string;
  resourceType: string;
  errorText: string;
}

export interface PublicPageRunRequest {
  runId: string;
  url: string;
  allowedOrigins: AllowedOrigin[];
  networkPolicy: NetworkPolicy;
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

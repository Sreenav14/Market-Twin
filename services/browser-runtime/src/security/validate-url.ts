import { isIP } from "node:net";

import type {
  AllowedOrigin,
  NetworkPolicy,
} from "../browser/types.js";

export class TargetUrlValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TargetUrlValidationError";
  }
}

function normalizeHostname(hostname: string): string {
  const withoutBrackets =
    hostname.startsWith("[") && hostname.endsWith("]")
      ? hostname.slice(1, -1)
      : hostname;

  return withoutBrackets.trim().toLowerCase().replace(/\.$/, "");
}

function isLoopbackHostname(hostname: string): boolean {
  return (
    hostname === "localhost" ||
    hostname.endsWith(".localhost") ||
    hostname === "localhost.localdomain"
  );
}

function isLoopbackIpv4Address(hostname: string): boolean {
  if (isIP(hostname) !== 4) {
    return false;
  }

  return Number(hostname.split(".")[0]) === 127;
}

function isBlockedIpv4Address(hostname: string): boolean {
  if (isIP(hostname) !== 4) {
    return false;
  }

  const octets = hostname.split(".").map(Number);
  const first = octets[0]!;
  const second = octets[1]!;

  return (
    first === 0 ||
    first === 10 ||
    first === 127 ||
    (first === 100 && second >= 64 && second <= 127) ||
    (first === 169 && second === 254) ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168)
  );
}

function isDirectIpv6Address(hostname: string): boolean {
  return isIP(hostname) === 6;
}

function isIpv6Loopback(hostname: string): boolean {
  return hostname === "::1";
}

function effectivePort(url: URL): number | null {
  if (url.port) {
    return Number(url.port);
  }

  return null;
}

function matchesAllowedOrigin(
  url: URL,
  origin: AllowedOrigin,
): boolean {
  const urlScheme = url.protocol.slice(0, -1).toLowerCase();
  const urlHostname = normalizeHostname(url.hostname);
  const allowedHostname = normalizeHostname(origin.hostname);

  const hostnameMatches = origin.includeSubdomains
    ? urlHostname === allowedHostname ||
      urlHostname.endsWith(`.${allowedHostname}`)
    : urlHostname === allowedHostname;

  return (
    urlScheme === origin.scheme &&
    hostnameMatches &&
    effectivePort(url) === origin.port
  );
}

function validateNetworkLocation(
  hostname: string,
  networkPolicy: NetworkPolicy,
): void {
  const normalizedHostname = normalizeHostname(hostname);

  if (isLoopbackHostname(normalizedHostname)) {
    if (networkPolicy === "local_development") {
      return;
    }

    throw new TargetUrlValidationError(
      "Loopback targets are only allowed in local development mode.",
    );
  }

  if (isLoopbackIpv4Address(normalizedHostname)) {
    if (networkPolicy === "local_development") {
      return;
    }

    throw new TargetUrlValidationError(
      "Loopback targets are only allowed in local development mode.",
    );
  }

  if (isBlockedIpv4Address(normalizedHostname)) {
    throw new TargetUrlValidationError(
      "Private, link-local, and reserved IPv4 targets are not allowed.",
    );
  }

  if (isDirectIpv6Address(normalizedHostname)) {
    if (
      networkPolicy === "local_development" &&
      isIpv6Loopback(normalizedHostname)
    ) {
      return;
    }

    throw new TargetUrlValidationError(
      "Direct IPv6 targets are not allowed.",
    );
  }
}

export function validateTargetUrl(
  rawUrl: string,
  allowedOrigins: AllowedOrigin[],
  networkPolicy: NetworkPolicy,
): URL {
  let parsedUrl: URL;

  try {
    parsedUrl = new URL(rawUrl);
  } catch {
    throw new TargetUrlValidationError(
      "Target URL must be a valid URL.",
    );
  }

  if (
    parsedUrl.protocol !== "http:" &&
    parsedUrl.protocol !== "https:"
  ) {
    throw new TargetUrlValidationError(
      "Only HTTP and HTTPS URLs are supported.",
    );
  }

  if (parsedUrl.username || parsedUrl.password) {
    throw new TargetUrlValidationError(
      "Credentials cannot be embedded in the URL.",
    );
  }

  if (allowedOrigins.length === 0) {
    throw new TargetUrlValidationError(
      "At least one allowed origin is required.",
    );
  }

  const isAllowed = allowedOrigins.some((origin) =>
    matchesAllowedOrigin(parsedUrl, origin),
  );

  if (!isAllowed) {
    throw new TargetUrlValidationError(
      `Target origin "${parsedUrl.origin}" is not allowed.`,
    );
  }

  validateNetworkLocation(
    parsedUrl.hostname,
    networkPolicy,
  );

  return parsedUrl;
}

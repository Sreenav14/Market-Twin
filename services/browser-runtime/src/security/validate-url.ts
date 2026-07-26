import { isIP } from "node:net";

export class TargetUrlValidationError extends Error {
    constructor(message: string) {
        super(message);
        this.name = "TargetUrlValidationError";
    }
}

function normalizeDomain(domain: string): string {
    return domain
    .trim()
    .toLowerCase()
    .replace(/\.$/, "");
}

function matchesAllowedDomain(
    hostname: string,
    allowedDomain: string,
): boolean {
    return (
        hostname == allowedDomain || 
        hostname.endsWith(`.${allowedDomain}`)
    );
}

function isLocalhost(hostname: string): boolean {
    return (hostname === "localhost" || hostname === "127.0.0.1" ||
    hostname.endsWith(".localhost") ||
    hostname === "localhost.localdomain" );
}

function isBlockedTpv4Address(hostname: string): boolean{
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
function removeIpv6Brackets(hostname: string): string {
    if (
      hostname.startsWith("[") &&
      hostname.endsWith("]")
    ) {
      return hostname.slice(1, -1);
    }
  
    return hostname;
  }
  
  function isDirectIpv6Address(hostname: string): boolean {
    const address = removeIpv6Brackets(hostname);
  
    return isIP(address) === 6;
  }

export function validateTargetUrl(
    rawUrl: string,
    allowedDomains: string[],
): URL {
    let parsedUrl: URL;

    try {
        parsedUrl = new URL(rawUrl);
    } catch {
        throw new TargetUrlValidationError(`Target URL must be a valid URL.`);
    }
    // URL.protocol includes the trailing colon (e.g. "https:")
    if (parsedUrl.protocol !== "http:" && parsedUrl.protocol !== "https:") {
        throw new TargetUrlValidationError("Only HTTP and HTTPS URLs are supported.");
    }

    if (parsedUrl.username || parsedUrl.password) {
        throw new TargetUrlValidationError(
            "Credentials are not embedded in the URL."
        );
    }

    const hostname = normalizeDomain(parsedUrl.hostname);
    
    if (isDirectIpv6Address(hostname)) {
        throw new TargetUrlValidationError(
          "Direct IPv6 targets are not allowed.",
        );
      }

    if (isLocalhost(hostname)) {
        throw new TargetUrlValidationError(
            "Localhost targets are not allowed."
        );
    }

    if (isBlockedTpv4Address(hostname)) {
        throw new TargetUrlValidationError(
            "Blocked IPv4 addresses are not allowed."
        );
    }   

    const normalizedAllowedDomains = allowedDomains.map(normalizeDomain).filter((domain) => domain.length > 0);

    if (normalizedAllowedDomains.length === 0) {
        throw new TargetUrlValidationError(
            "At least one allowed domain is required"
        );
    }

    const isAllowed = normalizedAllowedDomains.some(
        (allowedDomain) =>
            matchesAllowedDomain(hostname, allowedDomain),
    );

    if (!isAllowed) {
        throw new TargetUrlValidationError(`Target domain "${hostname}" is not allowed.`);
    }

    return parsedUrl;
}


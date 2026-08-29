import assert from "node:assert/strict";
import test from "node:test";

import {
  TargetUrlValidationError,
  validateTargetUrl,
} from "../src/security/validate-url.js";

import type { AllowedOrigin } from "../src/browser/types.js";

const exactExampleOrigin: AllowedOrigin[] = [
  {
    scheme: "https",
    hostname: "example.com",
    port: null,
    include_subdomains: false,
  },
];

test("allows an exact approved origin", () => {
  const result = validateTargetUrl(
    "https://example.com/path",
    exactExampleOrigin,
    "public_only",
  );

  assert.equal(result.hostname, "example.com");
});

test("blocks subdomains when include_subdomains is false", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "https://www.example.com",
        exactExampleOrigin,
        "public_only",
      ),
    TargetUrlValidationError,
  );
});

test("allows subdomains when include_subdomains is true", () => {
  const result = validateTargetUrl(
    "https://www.example.com",
    [
      {
        ...exactExampleOrigin[0]!,
        include_subdomains: true,
      },
    ],
    "public_only",
  );

  assert.equal(result.hostname, "www.example.com");
});

test("blocks domain suffix attacks", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "https://evil-example.com",
        [
          {
            ...exactExampleOrigin[0]!,
            include_subdomains: true,
          },
        ],
        "public_only",
      ),
    TargetUrlValidationError,
  );
});

test("blocks a different scheme", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "http://example.com",
        exactExampleOrigin,
        "public_only",
      ),
    /origin .* is not allowed/,
  );
});

test("blocks a different non-default port", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "https://example.com:8443",
        exactExampleOrigin,
        "public_only",
      ),
    /origin .* is not allowed/,
  );
});

test("allows an explicitly approved non-default port", () => {
  const result = validateTargetUrl(
    "https://example.com:8443",
    [
      {
        scheme: "https",
        hostname: "example.com",
        port: 8443,
        include_subdomains: false,
      },
    ],
    "public_only",
  );

  assert.equal(result.port, "8443");
});

test("blocks a domain outside the allowlist", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "https://example.org",
        exactExampleOrigin,
        "public_only",
      ),
    TargetUrlValidationError,
  );
});

test("blocks unsupported URL protocols", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "file:///secret.txt",
        exactExampleOrigin,
        "public_only",
      ),
    TargetUrlValidationError,
  );
});

test("blocks credentials embedded in a URL", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "https://user:password@example.com",
        exactExampleOrigin,
        "public_only",
      ),
    TargetUrlValidationError,
  );
});

test("blocks localhost in public-only mode", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "http://localhost:3000",
        [
          {
            scheme: "http",
            hostname: "localhost",
            port: 3000,
            include_subdomains: false,
          },
        ],
        "public_only",
      ),
    /only allowed in local development mode/,
  );
});

test("allows localhost in explicit local-development mode", () => {
  const result = validateTargetUrl(
    "http://localhost:3000",
    [
      {
        scheme: "http",
        hostname: "localhost",
        port: 3000,
        include_subdomains: false,
      },
    ],
    "local_development",
  );

  assert.equal(result.hostname, "localhost");
  assert.equal(result.port, "3000");
});

test("allows IPv4 loopback in explicit local-development mode", () => {
  const result = validateTargetUrl(
    "http://127.0.0.1:8000",
    [
      {
        scheme: "http",
        hostname: "127.0.0.1",
        port: 8000,
        include_subdomains: false,
      },
    ],
    "local_development",
  );

  assert.equal(result.hostname, "127.0.0.1");
});

test("blocks private IPv4 even in local-development mode", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "http://192.168.1.5",
        [
          {
            scheme: "http",
            hostname: "192.168.1.5",
            port: null,
            include_subdomains: false,
          },
        ],
        "local_development",
      ),
    /Private, link-local, and reserved IPv4 targets are not allowed/,
  );
});

test("blocks link-local and cloud metadata addresses", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "http://169.254.169.254/latest/meta-data",
        [
          {
            scheme: "http",
            hostname: "169.254.169.254",
            port: null,
            include_subdomains: false,
          },
        ],
        "local_development",
      ),
    TargetUrlValidationError,
  );
});

test("allows IPv6 loopback only in local-development mode", () => {
  const result = validateTargetUrl(
    "http://[::1]:8000",
    [
      {
        scheme: "http",
        hostname: "::1",
        port: 8000,
        include_subdomains: false,
      },
    ],
    "local_development",
  );

  assert.equal(result.hostname, "[::1]");
});

test("blocks directly entered public IPv6 addresses", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "https://[2606:4700:4700::1111]",
        [
          {
            scheme: "https",
            hostname: "2606:4700:4700::1111",
            port: null,
            include_subdomains: false,
          },
        ],
        "public_only",
      ),
    /Direct IPv6 targets are not allowed/,
  );
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  TargetUrlValidationError,
  validateTargetUrl,
} from "../src/security/validate-url.js";

test("allows an exact approved domain", () => {
  const result = validateTargetUrl(
    "https://example.com",
    ["example.com"],
  );

  assert.equal(result.hostname, "example.com");
});

test("allows a subdomain of an approved domain", () => {
  const result = validateTargetUrl(
    "https://www.example.com",
    ["example.com"],
  );

  assert.equal(result.hostname, "www.example.com");
});

test("blocks a domain outside the allowlist", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "https://example.org",
        ["example.com"],
      ),
    TargetUrlValidationError,
  );
});

test("blocks domain suffix attacks", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "https://evil-example.com",
        ["example.com"],
      ),
    TargetUrlValidationError,
  );
});

test("blocks unsupported URL protocols", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "file:///secret.txt",
        ["example.com"],
      ),
    TargetUrlValidationError,
  );
});

test("blocks credentials embedded in a URL", () => {
  assert.throws(
    () =>
      validateTargetUrl(
        "https://user:password@example.com",
        ["example.com"],
      ),
    TargetUrlValidationError,
  );
});

test("blocks localhost targets", () => {
    assert.throws(
        () => 
            validateTargetUrl(
                "http://localhost",
                ["localhost"],
            ),
        TargetUrlValidationError,
    );
});

test("blocks localhost subdomain", () => {
    assert.throws(
        () => 
            validateTargetUrl(
                "https://api.localhost",
                ["api.localhost"],
            ),
        TargetUrlValidationError,
    );
})

test("blocks IPv4 loopback addresses", () => {
    assert.throws(
      () =>
        validateTargetUrl(
          "http://127.0.0.1:8000",
          ["127.0.0.1"],
        ),
      TargetUrlValidationError,
    );
  });
  
  test("blocks 10.x private addresses", () => {
    assert.throws(
      () =>
        validateTargetUrl(
          "http://10.0.0.5",
          ["10.0.0.5"],
        ),
      TargetUrlValidationError,
    );
  });
  
  test("blocks 172.16 private addresses", () => {
    assert.throws(
      () =>
        validateTargetUrl(
          "http://172.16.0.5",
          ["172.16.0.5"],
        ),
      TargetUrlValidationError,
    );
  });
  
  test("blocks 192.168 private addresses", () => {
    assert.throws(
      () =>
        validateTargetUrl(
          "http://192.168.1.5",
          ["192.168.1.5"],
        ),
      TargetUrlValidationError,
    );
  });
  
  test("blocks link-local and cloud metadata addresses", () => {
    assert.throws(
      () =>
        validateTargetUrl(
          "http://169.254.169.254/latest/meta-data",
          ["169.254.169.254"],
        ),
      TargetUrlValidationError,
    );
  });
  test("blocks IPv6 loopback addresses", () => {
    assert.throws(
      () =>
        validateTargetUrl(
          "http://[::1]:8000",
          ["[::1]"],
        ),
      /Direct IPv6 targets are not allowed/,
    );
  });
  
  test("blocks directly entered public IPv6 addresses", () => {
    assert.throws(
      () =>
        validateTargetUrl(
          "https://[2606:4700:4700::1111]",
          ["[2606:4700:4700::1111]"],
        ),
      /Direct IPv6 targets are not allowed/,
    );
  });
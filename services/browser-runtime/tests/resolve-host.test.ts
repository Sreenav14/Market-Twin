import assert from "node:assert/strict";
import test from "node:test";

import {
  HostResolutionError,
  resolveAndValidateHost,
} from "../src/security/resolve-host.js";

import type { HostLookup } from "../src/security/resolve-host.js";

test("allows a hostname resolving to a public IPv4 address", async () => {
  const hostLookup: HostLookup = async () => [
    {
      address: "93.184.216.34",
      family: 4,
    },
  ];

  const result = await resolveAndValidateHost(
    "example.com",
    "public_only",
    hostLookup,
  );

  assert.equal(result[0]?.address, "93.184.216.34");
});

test("allows a hostname resolving to a public IPv6 address", async () => {
  const hostLookup: HostLookup = async () => [
    {
      address: "2606:4700:4700::1111",
      family: 6,
    },
  ];

  const result = await resolveAndValidateHost(
    "example.com",
    "public_only",
    hostLookup,
  );

  assert.equal(
    result[0]?.address,
    "2606:4700:4700::1111",
  );
});

test("blocks a hostname resolving to a private IPv4 address", async () => {
  const hostLookup: HostLookup = async () => [
    {
      address: "192.168.1.10",
      family: 4,
    },
  ];

  await assert.rejects(
    () =>
      resolveAndValidateHost(
        "malicious.example",
        "public_only",
        hostLookup,
      ),
    HostResolutionError,
  );
});

test("blocks loopback resolution in public-only mode", async () => {
  const hostLookup: HostLookup = async () => [
    {
      address: "127.0.0.1",
      family: 4,
    },
    {
      address: "::1",
      family: 6,
    },
  ];

  await assert.rejects(
    () =>
      resolveAndValidateHost(
        "localhost",
        "public_only",
        hostLookup,
      ),
    /resolved to blocked address/,
  );
});

test("allows loopback resolution in local-development mode", async () => {
  const hostLookup: HostLookup = async () => [
    {
      address: "127.0.0.1",
      family: 4,
    },
    {
      address: "::1",
      family: 6,
    },
  ];

  const result = await resolveAndValidateHost(
    "localhost",
    "local_development",
    hostLookup,
  );

  assert.equal(result.length, 2);
});

test("still blocks private addresses in local-development mode", async () => {
  const hostLookup: HostLookup = async () => [
    {
      address: "192.168.1.10",
      family: 4,
    },
  ];

  await assert.rejects(
    () =>
      resolveAndValidateHost(
        "internal.example",
        "local_development",
        hostLookup,
      ),
    /resolved to blocked address/,
  );
});

test("blocks a hostname when any resolved address is disallowed", async () => {
  const hostLookup: HostLookup = async () => [
    {
      address: "93.184.216.34",
      family: 4,
    },
    {
      address: "10.0.0.5",
      family: 4,
    },
  ];

  await assert.rejects(
    () =>
      resolveAndValidateHost(
        "mixed.example",
        "public_only",
        hostLookup,
      ),
    /resolved to blocked address/,
  );
});

test("blocks a hostname returning no addresses", async () => {
  const hostLookup: HostLookup = async () => [];

  await assert.rejects(
    () =>
      resolveAndValidateHost(
        "empty.example",
        "public_only",
        hostLookup,
      ),
    /returned no addresses/,
  );
});

test("handles DNS lookup failure", async () => {
  const hostLookup: HostLookup = async () => {
    throw new Error("DNS failure");
  };

  await assert.rejects(
    () =>
      resolveAndValidateHost(
        "missing.example",
        "public_only",
        hostLookup,
      ),
    /Unable to resolve target hostname/,
  );
});

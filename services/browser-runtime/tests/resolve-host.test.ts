import assert from "node:assert/strict";
import test from "node:test";

import {
  HostResolutionError,
  resolveAndValidatePublicHost,
} from "../src/security/resolve-host.js";

import type { HostLookup } from "../src/security/resolve-host.js";

test("allows a hostname resolving to a public IPv4 address", async () => {
  const hostLookup: HostLookup = async () => [
    {
      address: "93.184.216.34",
      family: 4,
    },
  ];

  const result = await resolveAndValidatePublicHost(
    "example.com",
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

  const result = await resolveAndValidatePublicHost(
    "example.com",
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
      resolveAndValidatePublicHost(
        "malicious.example",
        hostLookup,
      ),
    HostResolutionError,
  );
});

test("blocks a hostname resolving to IPv6 loopback", async () => {
  const hostLookup: HostLookup = async () => [
    {
      address: "::1",
      family: 6,
    },
  ];

  await assert.rejects(
    () =>
      resolveAndValidatePublicHost(
        "malicious.example",
        hostLookup,
      ),
    HostResolutionError,
  );
});

test("blocks a hostname when any resolved address is private", async () => {
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
      resolveAndValidatePublicHost(
        "mixed.example",
        hostLookup,
      ),
    /resolved to blocked address/,
  );
});

test("blocks a hostname returning no addresses", async () => {
  const hostLookup: HostLookup = async () => [];

  await assert.rejects(
    () =>
      resolveAndValidatePublicHost(
        "empty.example",
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
      resolveAndValidatePublicHost(
        "missing.example",
        hostLookup,
      ),
    /Unable to resolve target hostname/,
  );
});
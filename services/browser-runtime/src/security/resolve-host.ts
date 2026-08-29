import { lookup } from "node:dns/promises";

import ipaddr from "ipaddr.js";

import type { NetworkPolicy } from "../browser/types.js";

export interface ResolvedAddress {
  address: string;
  family: 4 | 6;
}

export type HostLookup = (
  hostname: string,
) => Promise<ResolvedAddress[]>;

export class HostResolutionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "HostResolutionError";
  }
}

async function systemHostLookup(
  hostname: string,
): Promise<ResolvedAddress[]> {
  const addresses = await lookup(hostname, {
    all: true,
    order: "verbatim",
  });

  return addresses.map(({ address, family }) => {
    if (family !== 4 && family !== 6) {
      throw new HostResolutionError(
        `Unsupported address family returned for "${hostname}".`,
      );
    }

    return {
      address,
      family,
    };
  });
}

function isAddressAllowed(
  address: string,
  networkPolicy: NetworkPolicy,
): boolean {
  try {
    const range = ipaddr.parse(address).range();

    if (range === "unicast") {
      return true;
    }

    return (
      networkPolicy === "local_development" &&
      range === "loopback"
    );
  } catch {
    return false;
  }
}

export async function resolveAndValidateHost(
  hostname: string,
  networkPolicy: NetworkPolicy,
  hostLookup: HostLookup = systemHostLookup,
): Promise<ResolvedAddress[]> {
  let addresses: ResolvedAddress[];

  try {
    addresses = await hostLookup(hostname);
  } catch {
    throw new HostResolutionError(
      `Unable to resolve target hostname "${hostname}".`,
    );
  }

  if (addresses.length === 0) {
    throw new HostResolutionError(
      `Target hostname "${hostname}" returned no addresses.`,
    );
  }

  const blockedAddress = addresses.find(
    ({ address }) =>
      !isAddressAllowed(address, networkPolicy),
  );

  if (blockedAddress) {
    throw new HostResolutionError(
      `Target hostname "${hostname}" resolved to blocked address "${blockedAddress.address}".`,
    );
  }

  return addresses;
}

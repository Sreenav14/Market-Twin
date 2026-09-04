"""DNS and resolved-IP validation for MarketTwin browser execution."""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable

from markettwin_execution_orchestrator.browser.contracts import (
    NetworkPolicy,
    ResolvedAddress,
)
from markettwin_execution_orchestrator.browser.errors import HostResolutionError

HostLookup = Callable[[str], Awaitable[tuple[ResolvedAddress, ...]]]


async def system_host_lookup(hostname: str) -> tuple[ResolvedAddress, ...]:
    """Resolve all stream-capable addresses without blocking the event loop."""

    loop = asyncio.get_running_loop()
    results = await loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    seen: set[tuple[str, int]] = set()
    addresses: list[ResolvedAddress] = []

    for family, _socktype, _proto, _canonname, sockaddr in results:
        if family == socket.AF_INET:
            address, version = str(sockaddr[0]), 4
        elif family == socket.AF_INET6:
            address, version = str(sockaddr[0]), 6
        else:
            continue
        key = (address, version)
        if key not in seen:
            seen.add(key)
            addresses.append(ResolvedAddress(address=address, family=version))

    return tuple(addresses)


def _is_address_allowed(address: str, network_policy: NetworkPolicy) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    if parsed.is_loopback:
        return network_policy == "local_development"
    return parsed.is_global


async def resolve_and_validate_host(
    hostname: str,
    network_policy: NetworkPolicy,
    host_lookup: HostLookup = system_host_lookup,
) -> tuple[ResolvedAddress, ...]:
    """Resolve a hostname and fail closed if any returned address is unsafe."""

    try:
        addresses = await host_lookup(hostname)
    except HostResolutionError:
        raise
    except Exception as exc:
        raise HostResolutionError(
            f'Unable to resolve target hostname "{hostname}".'
        ) from exc

    if not addresses:
        raise HostResolutionError(f'Target hostname "{hostname}" returned no addresses.')

    blocked = next(
        (
            address
            for address in addresses
            if not _is_address_allowed(address.address, network_policy)
        ),
        None,
    )
    if blocked is not None:
        raise HostResolutionError(
            f'Target hostname "{hostname}" resolved to blocked address "{blocked.address}".'
        )
    return addresses

from __future__ import annotations

import pytest
from markettwin_execution_orchestrator.browser.contracts import ResolvedAddress
from markettwin_execution_orchestrator.browser.errors import HostResolutionError
from markettwin_execution_orchestrator.browser.network import resolve_and_validate_host

pytestmark = pytest.mark.asyncio


async def test_allows_public_ipv4() -> None:
    async def lookup(_hostname: str) -> tuple[ResolvedAddress, ...]:
        return (ResolvedAddress("93.184.216.34", 4),)

    result = await resolve_and_validate_host("example.com", "public_only", lookup)
    assert result[0].address == "93.184.216.34"


async def test_allows_public_ipv6_from_dns() -> None:
    async def lookup(_hostname: str) -> tuple[ResolvedAddress, ...]:
        return (ResolvedAddress("2606:4700:4700::1111", 6),)

    result = await resolve_and_validate_host("example.com", "public_only", lookup)
    assert result[0].family == 6


async def test_blocks_private_ipv4() -> None:
    async def lookup(_hostname: str) -> tuple[ResolvedAddress, ...]:
        return (ResolvedAddress("192.168.1.10", 4),)

    with pytest.raises(HostResolutionError):
        await resolve_and_validate_host("malicious.example", "public_only", lookup)


async def test_blocks_loopback_public() -> None:
    async def lookup(_hostname: str) -> tuple[ResolvedAddress, ...]:
        return (ResolvedAddress("127.0.0.1", 4), ResolvedAddress("::1", 6))

    with pytest.raises(HostResolutionError, match="blocked address"):
        await resolve_and_validate_host("localhost", "public_only", lookup)


async def test_allows_loopback_local_development() -> None:
    async def lookup(_hostname: str) -> tuple[ResolvedAddress, ...]:
        return (ResolvedAddress("127.0.0.1", 4), ResolvedAddress("::1", 6))

    result = await resolve_and_validate_host("localhost", "local_development", lookup)
    assert len(result) == 2


async def test_blocks_private_address_local_development() -> None:
    async def lookup(_hostname: str) -> tuple[ResolvedAddress, ...]:
        return (ResolvedAddress("10.0.0.5", 4),)

    with pytest.raises(HostResolutionError):
        await resolve_and_validate_host("internal.example", "local_development", lookup)


async def test_blocks_if_any_resolved_address_is_unsafe() -> None:
    async def lookup(_hostname: str) -> tuple[ResolvedAddress, ...]:
        return (
            ResolvedAddress("93.184.216.34", 4),
            ResolvedAddress("10.0.0.5", 4),
        )

    with pytest.raises(HostResolutionError):
        await resolve_and_validate_host("mixed.example", "public_only", lookup)


async def test_blocks_empty_dns_result() -> None:
    async def lookup(_hostname: str) -> tuple[ResolvedAddress, ...]:
        return ()

    with pytest.raises(HostResolutionError, match="returned no addresses"):
        await resolve_and_validate_host("empty.example", "public_only", lookup)


async def test_wraps_dns_failure() -> None:
    async def lookup(_hostname: str) -> tuple[ResolvedAddress, ...]:
        raise OSError("dns failure")

    with pytest.raises(HostResolutionError, match="Unable to resolve"):
        await resolve_and_validate_host("missing.example", "public_only", lookup)

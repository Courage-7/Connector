from __future__ import annotations

import asyncio

import httpx
import pytest

from connector_service.core.exceptions import ProviderRequestError, ProviderUnavailableError
from connector_service.providers.supabase.client import SupabaseDataClient


def make_client(
    handler,
    *,
    api_key: str = "sb_secret_backend-key-with-sufficient-length",
    authorization_token: str | None = None,
    max_retries: int = 2,
    max_response_bytes: int = 1024 * 1024,
) -> SupabaseDataClient:
    return SupabaseDataClient(
        project_url="https://example.supabase.co",
        api_key=api_key,
        authorization_token=authorization_token,
        timeout_seconds=1,
        max_retries=max_retries,
        retry_base_seconds=0,
        max_response_bytes=max_response_bytes,
        transport=httpx.MockTransport(handler),
    )


def test_legacy_jwt_key_is_sent_as_bearer_token() -> None:
    legacy_key = "eyJheader.payload.signature"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == legacy_key
        assert request.headers["Authorization"] == f"Bearer {legacy_key}"
        return httpx.Response(200, json=[])

    async def run() -> None:
        async with make_client(handler, api_key=legacy_key) as client:
            await client.list_rows(
                resource="documents",
                columns=["id"],
                filters=[],
                order=[],
                limit=10,
                offset=0,
            )

    asyncio.run(run())


def test_idempotent_reads_retry_transient_provider_failures() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"message": "temporary"})
        return httpx.Response(200, json=[])

    async def run() -> None:
        async with make_client(handler) as client:
            await client.list_rows(
                resource="documents",
                columns=["id"],
                filters=[],
                order=[],
                limit=10,
                offset=0,
            )

    asyncio.run(run())
    assert attempts == 2


def test_rpc_post_is_never_retried() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"message": "temporary"})

    async def run() -> None:
        async with make_client(handler) as client:
            with pytest.raises(ProviderUnavailableError):
                await client.call_rpc(rpc="search_documents", arguments={}, limit=10)

    asyncio.run(run())
    assert attempts == 1


def test_oversized_provider_response_is_rejected() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"content": "x" * 2048}])

    async def run() -> None:
        async with make_client(handler, max_response_bytes=1024) as client:
            with pytest.raises(ProviderRequestError):
                await client.list_rows(
                    resource="documents",
                    columns=["content"],
                    filters=[],
                    order=[],
                    limit=10,
                    offset=0,
                )

    asyncio.run(run())

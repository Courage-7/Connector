"""Minimal backend-only Supabase Data API client."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from connector_service.core.exceptions import (
    ProviderAccessError,
    ProviderRequestError,
    ProviderUnavailableError,
)
from connector_service.providers.supabase.schemas import RowFilter, RowOrder


class SupabaseDataClient:
    """A deliberately small PostgREST client exposing only approved read operations."""

    def __init__(
        self,
        *,
        project_url: str,
        api_key: str,
        authorization_token: str | None,
        timeout_seconds: float,
        max_retries: int,
        retry_base_seconds: float,
        max_response_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds
        self._max_response_bytes = max_response_bytes
        headers = {
            "Accept": "application/json",
            "apikey": api_key,
            "User-Agent": "connector-service/0.1.0",
        }
        bearer_token = authorization_token or (api_key if self._looks_like_jwt(api_key) else None)
        if bearer_token is not None:
            headers["Authorization"] = f"Bearer {bearer_token}"
        self._client = httpx.AsyncClient(
            base_url=f"{project_url.rstrip('/')}/rest/v1/",
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
            headers=headers,
        )

    async def __aenter__(self) -> SupabaseDataClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self._client.aclose()

    async def list_rows(
        self,
        *,
        resource: str,
        columns: list[str],
        filters: list[RowFilter],
        order: list[RowOrder],
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        params: list[tuple[str, str]] = [("select", ",".join(columns)), ("limit", str(limit))]
        if offset:
            params.append(("offset", str(offset)))
        for item in filters:
            params.append((item.column, self._encode_filter(item)))
        if order:
            params.append(("order", ",".join(self._encode_order(item) for item in order)))
        response = await self._request("GET", resource, params=params)
        data = self._json(response)
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise ProviderRequestError()
        return data

    async def call_rpc(self, *, rpc: str, arguments: dict[str, Any], limit: int) -> Any:
        response = await self._request(
            "POST",
            f"rpc/{rpc}",
            params={"limit": str(limit)},
            json=arguments,
        )
        return self._json(response)

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        attempts = self._max_retries + 1 if method in {"GET", "HEAD"} else 1
        response: httpx.Response | None = None
        last_network_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = await self._client.request(method, path, **kwargs)
                last_network_error = None
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_network_error = exc
            should_retry = last_network_error is not None or (
                response is not None and response.status_code in {503, 520}
            )
            if not should_retry or attempt == attempts - 1:
                break
            await asyncio.sleep(self._retry_base_seconds * (2**attempt))
        if last_network_error is not None or response is None:
            raise ProviderUnavailableError() from last_network_error
        if response.status_code in {401, 403}:
            raise ProviderAccessError()
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderUnavailableError()
        if response.status_code >= 400:
            raise ProviderRequestError()
        if len(response.content) > self._max_response_bytes:
            raise ProviderRequestError("The provider response exceeded the configured size limit.")
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderRequestError() from exc

    @classmethod
    def _encode_filter(cls, item: RowFilter) -> str:
        if item.operator.value == "in":
            encoded = ",".join(cls._encode_scalar(value) for value in item.value)
            return f"in.({encoded})"
        return f"{item.operator.value}.{cls._encode_scalar(item.value)}"

    @staticmethod
    def _encode_scalar(value: Any) -> str:
        if value is None:
            return "null"
        if value is True:
            return "true"
        if value is False:
            return "false"
        if isinstance(value, (int, float)):
            return str(value)
        text = str(value)
        if any(character in text for character in {",", "(", ")", '"', "\\"}):
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return text

    @staticmethod
    def _encode_order(item: RowOrder) -> str:
        value = f"{item.column}.{item.direction.value}"
        return f"{value}.nulls{item.nulls}" if item.nulls else value

    @staticmethod
    def _looks_like_jwt(value: str) -> bool:
        return value.count(".") == 2 and value.startswith("eyJ")

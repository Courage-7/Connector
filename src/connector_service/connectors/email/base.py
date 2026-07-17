"""Defensive HTTP primitives and protocol for email providers."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from connector_service.config import Settings
from connector_service.connectors.email.schemas import (
    AttachmentMetadata,
    DraftResponse,
    EmailCompose,
    EmailIdentity,
    MailFolder,
    MessageDetail,
    MessagePage,
    MessageSearch,
    MessageThread,
)
from connector_service.connectors.oauth import OAuthTokenSet
from connector_service.core.exceptions import (
    ProviderAccessError,
    ProviderRequestError,
    ProviderUnavailableError,
)


class EmailClient(Protocol):
    provider: str

    def authorization_url(
        self,
        *,
        state: str,
        code_challenge: str,
        login_hint: str | None,
    ) -> str: ...

    async def exchange_code(self, *, code: str, code_verifier: str) -> OAuthTokenSet: ...

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokenSet: ...

    async def revoke(self, token: str) -> None: ...

    async def identity(self, access_token: str) -> tuple[str, str]: ...

    async def list_folders(self, access_token: str) -> list[MailFolder]: ...

    async def search_messages(
        self,
        access_token: str,
        request: MessageSearch,
    ) -> MessagePage: ...

    async def get_message(self, access_token: str, message_id: str) -> MessageDetail: ...

    async def get_thread(self, access_token: str, thread_id: str) -> MessageThread: ...

    async def list_attachments(
        self,
        access_token: str,
        message_id: str,
    ) -> list[AttachmentMetadata]: ...

    async def create_draft(self, access_token: str, message: EmailCompose) -> DraftResponse: ...

    async def send_message(self, access_token: str, message: EmailCompose) -> None: ...


class DefensiveProviderClient:
    provider = "Email provider"

    def __init__(
        self,
        settings: Settings,
        *,
        api_base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._api_base_url = api_base_url.rstrip("/")
        self._transport = transport

    async def _request(
        self,
        method: str,
        path: str,
        *,
        access_token: str | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        base_url: str | None = None,
    ) -> httpx.Response:
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "connector-service/0.3.0",
            **(headers or {}),
        }
        if access_token:
            request_headers["Authorization"] = f"Bearer {access_token}"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.provider_timeout_seconds),
                transport=self._transport,
                headers=request_headers,
                follow_redirects=False,
            ) as client:
                endpoint = f"{(base_url or self._api_base_url).rstrip('/')}/{path.lstrip('/')}"
                response = await client.request(
                    method,
                    endpoint,
                    params=params,
                    data=form,
                    json=json_body,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderUnavailableError() from exc
        if response.status_code in {401, 403}:
            raise ProviderAccessError()
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderUnavailableError()
        if response.status_code >= 400:
            raise ProviderRequestError(f"{self.provider} rejected the request.")
        if len(response.content) > self._settings.max_provider_response_bytes:
            raise ProviderRequestError("The provider response exceeded the configured size limit.")
        return response

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._request(method, path, **kwargs)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderRequestError(f"{self.provider} returned an invalid response.") from exc


def identity(address: str | None, name: str | None = None) -> EmailIdentity | None:
    if not address:
        return None
    return EmailIdentity(address=address, display_name=name or None)

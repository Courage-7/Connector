"""Supabase OAuth and Management API client for user-authorized connections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from connector_service.config import Settings
from connector_service.core.exceptions import (
    InvalidRequestError,
    ProviderAccessError,
    ProviderRequestError,
    ProviderUnavailableError,
)


@dataclass(frozen=True, slots=True)
class OAuthTokens:
    access_token: str
    refresh_token: str
    token_type: str
    expires_at: datetime

    @classmethod
    def from_response(
        cls,
        payload: Any,
        *,
        fallback_refresh_token: str | None = None,
        now: datetime | None = None,
    ) -> OAuthTokens:
        if not isinstance(payload, dict):
            raise ProviderRequestError("Supabase returned an invalid OAuth response.")
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token") or fallback_refresh_token
        token_type = payload.get("token_type", "Bearer")
        expires_in = payload.get("expires_in")
        if (
            not isinstance(access_token, str)
            or not access_token
            or not isinstance(refresh_token, str)
            or not refresh_token
            or not isinstance(token_type, str)
            or token_type.lower() != "bearer"
            or not isinstance(expires_in, int)
            or expires_in <= 0
        ):
            raise ProviderRequestError("Supabase returned an invalid OAuth response.")
        issued_at = now or datetime.now(UTC)
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_at=issued_at + timedelta(seconds=expires_in),
        )

    @classmethod
    def from_secret(cls, value: dict[str, Any]) -> OAuthTokens:
        access_token = value.get("access_token")
        refresh_token = value.get("refresh_token")
        token_type = value.get("token_type")
        raw_expires_at = value.get("expires_at")
        if not all(isinstance(item, str) and item for item in (access_token, refresh_token)):
            raise ProviderAccessError()
        if token_type != "Bearer" or not isinstance(raw_expires_at, str):
            raise ProviderAccessError()
        try:
            expires_at = datetime.fromisoformat(raw_expires_at)
        except ValueError as exc:
            raise ProviderAccessError() from exc
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=token_type,
            expires_at=expires_at,
        )

    def secret_document(self) -> dict[str, str]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expires_at": self.expires_at.isoformat(),
        }


class SupabaseManagementClient:
    """Small, defensive client for the OAuth and read-only Management APIs."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def authorization_url(
        self,
        *,
        state: str,
        code_challenge: str,
        organization_slug: str | None,
    ) -> str:
        client_id, _client_secret = self._oauth_credentials()
        parameters = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": self._settings.supabase_oauth_redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if organization_slug:
            parameters["organization_slug"] = organization_slug
        base_url = self._settings.supabase_management_api_url
        return f"{base_url}/v1/oauth/authorize?{urlencode(parameters)}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> OAuthTokens:
        payload = await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._settings.supabase_oauth_redirect_uri,
                "code_verifier": code_verifier,
            }
        )
        return OAuthTokens.from_response(payload)

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        payload = await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )
        return OAuthTokens.from_response(payload, fallback_refresh_token=refresh_token)

    async def revoke(self, refresh_token: str) -> None:
        client_id, client_secret = self._oauth_credentials()
        await self._request_json(
            "POST",
            "/v1/oauth/revoke",
            json_body={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
        )

    async def list_projects(self, access_token: str) -> list[dict[str, Any]]:
        payload = await self._request_json("GET", "/v1/projects", access_token=access_token)
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
            raise ProviderRequestError()
        return payload

    async def run_read_only_query(
        self,
        *,
        access_token: str,
        project_ref: str,
        query: str,
        parameters: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        payload = await self._request_json(
            "POST",
            f"/v1/projects/{project_ref}/database/query/read-only",
            access_token=access_token,
            json_body={"query": query, "parameters": parameters or []},
        )
        rows: Any = payload.get("result") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ProviderRequestError("Supabase returned an unexpected query response.")
        return rows

    async def _token_request(self, form: dict[str, str]) -> Any:
        client_id, client_secret = self._oauth_credentials()
        return await self._request_json(
            "POST",
            "/v1/oauth/token",
            form=form,
            basic_auth=httpx.BasicAuth(client_id, client_secret),
        )

    def _oauth_credentials(self) -> tuple[str, str]:
        client_id = self._settings.supabase_oauth_client_id
        client_secret = self._settings.supabase_oauth_client_secret
        if not client_id or client_secret is None:
            raise InvalidRequestError(
                "Supabase OAuth is not configured for this connector service."
            )
        return client_id, client_secret.get_secret_value()

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        access_token: str | None = None,
        form: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        basic_auth: httpx.BasicAuth | None = None,
    ) -> Any:
        headers = {"Accept": "application/json", "User-Agent": "connector-service/0.2.0"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.supabase_management_api_url,
                timeout=httpx.Timeout(self._settings.provider_timeout_seconds),
                transport=self._transport,
                headers=headers,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    data=form,
                    json=json_body,
                    auth=basic_auth,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderUnavailableError() from exc
        if response.status_code in {401, 403}:
            raise ProviderAccessError()
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderUnavailableError()
        if response.status_code >= 400:
            raise ProviderRequestError()
        if len(response.content) > self._settings.max_provider_response_bytes:
            raise ProviderRequestError("The provider response exceeded the configured size limit.")
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderRequestError() from exc

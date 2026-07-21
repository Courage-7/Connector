"""Static development and Supabase JWT Bearer authenticators."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx
import jwt

from connector_service.core.exceptions import AuthenticationError
from connector_service.identity.principal import Principal


class Authenticator(Protocol):
    async def authenticate(self, token: str) -> Principal: ...


@dataclass(frozen=True, slots=True)
class StaticBearerAuthenticator:
    token: str
    subject: str

    async def authenticate(self, token: str) -> Principal:
        if not hmac.compare_digest(token.encode(), self.token.encode()):
            raise AuthenticationError()
        return Principal(
            subject=self.subject,
            tenant_id=self.subject,
            authentication_method="static_bearer",
        )


class SupabaseJwtAuthenticator:
    """Verify Supabase Auth access tokens against the project's JWKS."""

    def __init__(
        self,
        *,
        auth_url: str,
        audience: str,
        cache_seconds: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._auth_url = auth_url.rstrip("/")
        self._audience = audience
        self._cache_seconds = cache_seconds
        self._transport = transport
        self._jwks: dict[str, Any] | None = None
        self._jwks_expires_at = datetime.min.replace(tzinfo=UTC)

    async def authenticate(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
            key_id = header.get("kid")
            algorithm = header.get("alg")
            if not isinstance(key_id, str) or algorithm not in {"RS256", "ES256"}:
                raise AuthenticationError()
            jwks = await self._get_jwks()
            raw_key = next(
                (
                    item
                    for item in jwks.get("keys", [])
                    if isinstance(item, dict) and item.get("kid") == key_id
                ),
                None,
            )
            if raw_key is None:
                self._jwks_expires_at = datetime.min.replace(tzinfo=UTC)
                jwks = await self._get_jwks()
                raw_key = next(
                    (
                        item
                        for item in jwks.get("keys", [])
                        if isinstance(item, dict) and item.get("kid") == key_id
                    ),
                    None,
                )
            if raw_key is None:
                raise AuthenticationError()
            signing_key = jwt.PyJWK.from_dict(raw_key, algorithm=algorithm).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=[algorithm],
                audience=self._audience,
                issuer=f"{self._auth_url}/auth/v1",
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        except (jwt.PyJWTError, ValueError, TypeError, AuthenticationError) as exc:
            raise AuthenticationError() from exc
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AuthenticationError()
        app_metadata = claims.get("app_metadata")
        tenant = app_metadata.get("tenant_id") if isinstance(app_metadata, dict) else None
        return Principal(
            subject=subject,
            tenant_id=tenant if isinstance(tenant, str) and tenant else subject,
            authentication_method="supabase_jwt",
        )

    async def _get_jwks(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        if self._jwks is not None and now < self._jwks_expires_at:
            return self._jwks
        try:
            async with httpx.AsyncClient(
                timeout=10,
                transport=self._transport,
                trust_env=False,
            ) as client:
                response = await client.get(f"{self._auth_url}/auth/v1/.well-known/jwks.json")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthenticationError() from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
            raise AuthenticationError()
        self._jwks = payload
        self._jwks_expires_at = now + timedelta(seconds=self._cache_seconds)
        return payload

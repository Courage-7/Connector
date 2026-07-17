"""Provider-neutral OAuth 2.0 helpers shared by connection adapters."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from connector_service.core.exceptions import ProviderAccessError, ProviderRequestError


@dataclass(frozen=True, slots=True)
class OAuthMaterial:
    state: str
    state_digest: bytes
    code_verifier: str
    code_challenge: str


@dataclass(frozen=True, slots=True)
class OAuthTokenSet:
    access_token: str
    refresh_token: str
    token_type: str
    expires_at: datetime
    scope: str | None = None

    @classmethod
    def from_response(
        cls,
        payload: Any,
        *,
        provider: str,
        fallback_refresh_token: str | None = None,
        now: datetime | None = None,
    ) -> OAuthTokenSet:
        if not isinstance(payload, dict):
            raise ProviderRequestError(f"{provider} returned an invalid OAuth response.")
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token") or fallback_refresh_token
        token_type = payload.get("token_type", "Bearer")
        expires_in = payload.get("expires_in")
        scope = payload.get("scope")
        if (
            not isinstance(access_token, str)
            or not access_token
            or not isinstance(refresh_token, str)
            or not refresh_token
            or not isinstance(token_type, str)
            or token_type.lower() != "bearer"
            or not isinstance(expires_in, int)
            or expires_in <= 0
            or (scope is not None and not isinstance(scope, str))
        ):
            raise ProviderRequestError(f"{provider} returned an invalid OAuth response.")
        issued_at = now or datetime.now(UTC)
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_at=issued_at + timedelta(seconds=expires_in),
            scope=scope,
        )

    @classmethod
    def from_secret(cls, value: dict[str, Any]) -> OAuthTokenSet:
        access_token = value.get("access_token")
        refresh_token = value.get("refresh_token")
        token_type = value.get("token_type")
        raw_expires_at = value.get("expires_at")
        scope = value.get("scope")
        if not all(isinstance(item, str) and item for item in (access_token, refresh_token)):
            raise ProviderAccessError()
        if (
            token_type != "Bearer"
            or not isinstance(raw_expires_at, str)
            or (scope is not None and not isinstance(scope, str))
        ):
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
            scope=scope,
        )

    def secret_document(self) -> dict[str, str]:
        document = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expires_at": self.expires_at.isoformat(),
        }
        if self.scope is not None:
            document["scope"] = self.scope
        return document


def create_oauth_material() -> OAuthMaterial:
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    challenge_bytes = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode("ascii").rstrip("=")
    return OAuthMaterial(
        state=state,
        state_digest=hashlib.sha256(state.encode("ascii")).digest(),
        code_verifier=code_verifier,
        code_challenge=code_challenge,
    )


def digest_oauth_state(state: str) -> bytes:
    return hashlib.sha256(state.encode("utf-8")).digest()

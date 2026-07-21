"""Production Supabase Auth JWT verification tests."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from connector_service.core.exceptions import AuthenticationError
from connector_service.identity.authenticators import SupabaseJwtAuthenticator


def test_supabase_jwt_authenticator_verifies_jwks_token() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = "test-key"

    def jwks(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/v1/.well-known/jwks.json"
        return httpx.Response(200, json={"keys": [jwk]})

    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "auth-user",
            "iss": "https://example.supabase.co/auth/v1",
            "aud": "authenticated",
            "exp": now + timedelta(minutes=5),
            "app_metadata": {"tenant_id": "tenant-one"},
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    authenticator = SupabaseJwtAuthenticator(
        auth_url="https://example.supabase.co",
        audience="authenticated",
        cache_seconds=300,
        transport=httpx.MockTransport(jwks),
    )
    principal = asyncio.run(authenticator.authenticate(token))
    assert principal.subject == "auth-user"
    assert principal.tenant_id == "tenant-one"

    with pytest.raises(AuthenticationError):
        asyncio.run(authenticator.authenticate(token + "tampered"))

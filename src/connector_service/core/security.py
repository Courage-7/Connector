"""Credential encryption, API-key hashing, and constant-time comparisons."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from connector_service.core.exceptions import AuthenticationError, ServiceError


class CredentialDecryptionError(ServiceError):
    code = "credential_decryption_failed"
    message = "The stored provider credential could not be decrypted."


class CredentialCipher:
    """Authenticated encryption for provider credential documents."""

    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("credential_encryption_key must be a valid Fernet key") from exc

    def encrypt(self, value: dict[str, Any]) -> bytes:
        payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return self._fernet.encrypt(payload)

    def decrypt(self, value: bytes) -> dict[str, Any]:
        try:
            payload = self._fernet.decrypt(value)
            decoded = json.loads(payload)
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CredentialDecryptionError() from exc
        if not isinstance(decoded, dict):
            raise CredentialDecryptionError()
        return decoded


@dataclass(frozen=True, slots=True)
class ApiKeyMaterial:
    """One-time plaintext key plus its persistable verification fields."""

    plaintext: str
    prefix: str
    salt: bytes
    digest: bytes


class ApiKeyManager:
    """Create and verify project API keys without storing plaintext."""

    scheme = "csp"

    @classmethod
    def create(cls) -> ApiKeyMaterial:
        prefix = secrets.token_hex(6)
        secret = secrets.token_urlsafe(32)
        salt = secrets.token_bytes(16)
        digest = cls._derive(secret, salt)
        return ApiKeyMaterial(
            plaintext=f"{cls.scheme}_{prefix}_{secret}",
            prefix=prefix,
            salt=salt,
            digest=digest,
        )

    @classmethod
    def parse(cls, plaintext: str) -> tuple[str, str]:
        try:
            scheme, prefix, secret = plaintext.split("_", maxsplit=2)
        except ValueError as exc:
            raise AuthenticationError() from exc
        if scheme != cls.scheme or len(prefix) != 12 or not secret:
            raise AuthenticationError()
        return prefix, secret

    @classmethod
    def verify(cls, secret: str, salt: bytes, expected_digest: bytes) -> bool:
        actual = cls._derive(secret, salt)
        return hmac.compare_digest(actual, expected_digest)

    @staticmethod
    def _derive(secret: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            secret.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        )


def create_opaque_token() -> tuple[str, bytes]:
    """Create a one-time token and the SHA-256 digest safe to persist."""

    plaintext = secrets.token_urlsafe(32)
    return plaintext, digest_opaque_token(plaintext)


def digest_opaque_token(plaintext: str) -> bytes:
    """Digest an opaque bearer token for indexed database lookup."""

    return hashlib.sha256(plaintext.encode("utf-8")).digest()


def secrets_equal(left: str, right: str) -> bool:
    """Compare secret text without leaking prefix timing information."""

    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))

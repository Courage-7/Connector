"""Authenticated encryption for provider tokens and OAuth context."""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from connector_service.core.exceptions import ServiceError


class SecretDecryptionError(ServiceError):
    code = "secret_decryption_failed"
    message = "Stored connection data could not be decrypted."


class SecretCipher:
    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc

    def encrypt(self, value: dict[str, Any]) -> bytes:
        payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        return self._fernet.encrypt(payload)

    def decrypt(self, value: bytes) -> dict[str, Any]:
        try:
            decoded = json.loads(self._fernet.decrypt(value))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SecretDecryptionError() from exc
        if not isinstance(decoded, dict):
            raise SecretDecryptionError()
        return decoded

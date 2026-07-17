from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from connector_service.core.exceptions import AuthenticationError, InvalidCursorError
from connector_service.core.pagination import CursorCodec, query_fingerprint
from connector_service.core.security import ApiKeyManager, CredentialCipher


def test_credentials_are_encrypted_and_authenticated() -> None:
    cipher = CredentialCipher(Fernet.generate_key().decode())
    secret = {"project_url": "https://example.supabase.co", "api_key": "secret"}

    encrypted = cipher.encrypt(secret)

    assert b"secret" not in encrypted
    assert cipher.decrypt(encrypted) == secret


def test_api_keys_are_one_way_verifiable() -> None:
    material = ApiKeyManager.create()
    prefix, secret = ApiKeyManager.parse(material.plaintext)

    assert prefix == material.prefix
    assert ApiKeyManager.verify(secret, material.salt, material.digest)
    assert not ApiKeyManager.verify("wrong", material.salt, material.digest)
    assert material.plaintext.encode() not in material.digest


def test_invalid_api_key_shape_is_rejected() -> None:
    with pytest.raises(AuthenticationError):
        ApiKeyManager.parse("not-a-project-key")


def test_cursor_is_bound_to_query_and_detects_tampering() -> None:
    codec = CursorCodec("a-signing-key-longer-than-thirty-two-characters")
    fingerprint = query_fingerprint({"resource": "documents", "limit": 25})
    cursor = codec.encode(offset=25, fingerprint=fingerprint)

    assert codec.decode(cursor, expected_fingerprint=fingerprint).offset == 25
    with pytest.raises(InvalidCursorError):
        codec.decode(cursor, expected_fingerprint=query_fingerprint({"resource": "users"}))
    with pytest.raises(InvalidCursorError):
        codec.decode(
            cursor[:-1] + ("A" if cursor[-1] != "A" else "B"),
            expected_fingerprint=fingerprint,
        )

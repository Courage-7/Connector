"""Opaque HMAC-signed pagination cursors."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from connector_service.core.exceptions import InvalidCursorError


def query_fingerprint(value: Any) -> str:
    """Return a stable digest binding a cursor to a normalized query."""

    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class CursorPayload:
    offset: int
    fingerprint: str


class CursorCodec:
    """Encode and validate cursor state without exposing mutable offsets."""

    def __init__(self, signing_key: str) -> None:
        self._key = signing_key.encode("utf-8")

    def encode(self, *, offset: int, fingerprint: str) -> str:
        payload = json.dumps(
            {"v": 1, "offset": offset, "fingerprint": fingerprint},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.new(self._key, payload, hashlib.sha256).digest()
        return self._b64(payload + signature)

    def decode(self, cursor: str, *, expected_fingerprint: str) -> CursorPayload:
        try:
            raw = self._unb64(cursor)
            payload, signature = raw[:-32], raw[-32:]
            expected = hmac.new(self._key, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise InvalidCursorError()
            decoded = json.loads(payload)
            offset = decoded["offset"]
            fingerprint = decoded["fingerprint"]
            if (
                decoded.get("v") != 1
                or not isinstance(offset, int)
                or offset < 0
                or fingerprint != expected_fingerprint
            ):
                raise InvalidCursorError()
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise InvalidCursorError() from exc
        return CursorPayload(offset=offset, fingerprint=fingerprint)

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _unb64(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)

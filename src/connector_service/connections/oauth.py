"""Provider-neutral OAuth state and PKCE helpers."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OAuthMaterial:
    state: str
    state_digest: bytes
    code_verifier: str
    code_challenge: str


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

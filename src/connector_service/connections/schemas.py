"""Connection and OAuth API contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from connector_service.core.contracts import StrictModel


class SupabaseAuthorizationRequest(StrictModel):
    organization_slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )


class AuthorizationStartResponse(StrictModel):
    authorization_url: str
    expires_at: datetime


class ConnectionResponse(StrictModel):
    id: str
    provider: str
    status: str
    external_reference: str | None
    display_name: str | None
    scopes: list[str]
    created_at: datetime


class OAuthCallbackResponse(StrictModel):
    connection: ConnectionResponse
    next_step: str

"""Administrative request and response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from connector_service.core.contracts import StrictModel
from connector_service.providers.supabase.schemas import (
    SupabaseAction,
    SupabaseCredentialInput,
    SupabaseGrantPolicy,
)


class CredentialCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    connector: Literal["supabase"]
    secret: SupabaseCredentialInput


class CredentialResponse(StrictModel):
    id: str
    name: str
    connector: str


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class ProjectCreatedResponse(StrictModel):
    id: str
    name: str
    api_key: str
    warning: str = "Store this API key now. It cannot be retrieved later."


class GrantCreate(StrictModel):
    project_id: str
    credential_id: str
    connector: Literal["supabase"]
    actions: list[SupabaseAction] = Field(min_length=1)
    policy: SupabaseGrantPolicy
    description: str | None = Field(default=None, max_length=1000)


class GrantResponse(StrictModel):
    id: str
    project_id: str
    credential_id: str
    connector: str
    actions: list[str]

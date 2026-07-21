"""Explicit configuration consumed by the Supabase provider adapter."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupabaseProviderConfig:
    client_id: str | None
    client_secret: str | None
    redirect_uri: str
    management_api_url: str
    timeout_seconds: float
    max_response_bytes: int

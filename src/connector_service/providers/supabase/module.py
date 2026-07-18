"""Supabase provider composition."""

from __future__ import annotations

import httpx

from connector_service.config import Settings
from connector_service.core.pagination import CursorCodec
from connector_service.providers.catalog import ProviderCapability, ProviderModule
from connector_service.providers.supabase.connector import SupabaseConnector
from connector_service.providers.supabase.management import SupabaseManagementClient


def build_supabase_module(
    settings: Settings,
    cursor_codec: CursorCodec,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderModule:
    management = SupabaseManagementClient(settings, transport=transport)
    return ProviderModule(
        name="supabase",
        display_name="Supabase",
        capabilities=frozenset(
            {
                ProviderCapability.ACTIONS,
                ProviderCapability.DATABASE,
                ProviderCapability.OAUTH,
            }
        ),
        configured=bool(
            settings.supabase_oauth_client_id and settings.supabase_oauth_client_secret is not None
        ),
        connectors=(SupabaseConnector(settings, cursor_codec),),
        services={SupabaseManagementClient: management},
    )

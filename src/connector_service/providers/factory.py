"""Composition root for provider modules."""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from connector_service.config import Settings
from connector_service.core.pagination import CursorCodec
from connector_service.providers.catalog import ProviderCatalog, ProviderModule
from connector_service.providers.gmail.module import build_gmail_module
from connector_service.providers.outlook.module import build_outlook_module
from connector_service.providers.supabase.module import build_supabase_module

ProviderTransportMap = Mapping[str, httpx.AsyncBaseTransport]


def build_provider_catalog(
    settings: Settings,
    cursor_codec: CursorCodec,
    *,
    transports: ProviderTransportMap | None = None,
) -> ProviderCatalog:
    """Construct only the providers selected for this deployment."""

    provider_transports = transports or {}
    builders = {
        "gmail": lambda: build_gmail_module(
            settings,
            transport=provider_transports.get("gmail"),
        ),
        "outlook": lambda: build_outlook_module(
            settings,
            transport=provider_transports.get("outlook"),
        ),
        "supabase": lambda: build_supabase_module(
            settings,
            cursor_codec,
            transport=provider_transports.get("supabase"),
        ),
    }
    modules: list[ProviderModule] = []
    for name in settings.enabled_provider_names:
        modules.append(builders[name]())
    return ProviderCatalog(modules)

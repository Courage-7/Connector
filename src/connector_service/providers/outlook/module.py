"""Microsoft Outlook provider composition."""

from __future__ import annotations

import httpx

from connector_service.config import Settings
from connector_service.providers.catalog import ProviderCapability, ProviderModule
from connector_service.providers.outlook.client import OutlookClient


def build_outlook_module(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderModule:
    client = OutlookClient(settings, transport=transport)
    return ProviderModule(
        name="outlook",
        display_name="Microsoft Outlook",
        capabilities=frozenset(
            {
                ProviderCapability.OAUTH,
                ProviderCapability.EMAIL,
                ProviderCapability.EMAIL_SEND,
                ProviderCapability.CALENDAR,
                ProviderCapability.TEAMS,
            }
        ),
        configured=bool(
            settings.outlook_oauth_client_id and settings.outlook_oauth_client_secret is not None
        ),
        email_client=client,
        calendar_client=client,
        teams_client=client,
    )

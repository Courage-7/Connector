"""Gmail provider composition."""

from __future__ import annotations

import httpx

from connector_service.config import Settings
from connector_service.providers.catalog import ProviderCapability, ProviderModule
from connector_service.providers.gmail.client import GmailClient


def build_gmail_module(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderModule:
    return ProviderModule(
        name="gmail",
        display_name="Gmail",
        capabilities=frozenset(
            {
                ProviderCapability.OAUTH,
                ProviderCapability.EMAIL,
                ProviderCapability.EMAIL_SEND,
            }
        ),
        configured=bool(
            settings.gmail_oauth_client_id and settings.gmail_oauth_client_secret is not None
        ),
        email_client=GmailClient(settings, transport=transport),
    )

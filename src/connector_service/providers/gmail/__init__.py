"""Gmail provider module."""

from connector_service.providers.gmail.client import GmailClient
from connector_service.providers.gmail.module import build_gmail_module

__all__ = ["GmailClient", "build_gmail_module"]

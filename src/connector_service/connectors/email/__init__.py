"""User-authorized email provider adapters."""

from connector_service.connectors.email.gmail import GmailClient
from connector_service.connectors.email.outlook import OutlookClient

__all__ = ["GmailClient", "OutlookClient"]

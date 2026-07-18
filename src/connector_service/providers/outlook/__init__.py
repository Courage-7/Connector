"""Microsoft Outlook provider module."""

from connector_service.providers.outlook.client import OutlookClient
from connector_service.providers.outlook.module import build_outlook_module

__all__ = ["OutlookClient", "build_outlook_module"]

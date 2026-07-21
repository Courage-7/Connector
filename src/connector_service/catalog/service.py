"""Static product catalog with runtime configuration status."""

from __future__ import annotations

from connector_service.bootstrap.config import Settings
from connector_service.catalog.models import ProviderManifest, ToolManifest
from connector_service.core.exceptions import NotFoundError


def _tool(
    name: str,
    display_name: str,
    description: str,
    capability: str,
    *,
    write: bool = False,
    implemented: bool,
) -> ToolManifest:
    return ToolManifest(
        name=name,
        display_name=display_name,
        description=description,
        capability=capability,
        operation_type="write" if write else "read",
        implemented=implemented,
    )


class ProviderCatalogService:
    def __init__(self, settings: Settings) -> None:
        self._providers = {provider.name: provider for provider in self._build_manifests(settings)}

    def list_providers(self) -> list[ProviderManifest]:
        return [self._providers[name] for name in sorted(self._providers)]

    def get_provider(self, name: str) -> ProviderManifest:
        provider = self._providers.get(name)
        if provider is None:
            raise NotFoundError("The requested provider does not exist.")
        return provider

    @staticmethod
    def _build_manifests(settings: Settings) -> list[ProviderManifest]:
        supabase_tools = [
            _tool(
                "list_projects",
                "List projects",
                "List authorized Supabase projects.",
                "projects",
                implemented=True,
            ),
            _tool(
                "select_project",
                "Select project",
                "Bind a connection to one Supabase project.",
                "projects",
                write=True,
                implemented=True,
            ),
            _tool(
                "list_tables",
                "List tables",
                "List readable tables and views.",
                "database",
                implemented=True,
            ),
            _tool(
                "describe_table",
                "Describe table",
                "Return live column metadata.",
                "database",
                implemented=True,
            ),
            _tool(
                "query_table",
                "Query table",
                "Run a bounded structured read-only query.",
                "database",
                implemented=True,
            ),
        ]
        google_tools = [
            _tool(
                "search_email", "Search email", "Search Gmail threads.", "email", implemented=False
            ),
            _tool(
                "get_email_thread",
                "Get email thread",
                "Retrieve a Gmail thread.",
                "email",
                implemented=False,
            ),
            _tool(
                "create_email_draft",
                "Create email draft",
                "Create a Gmail draft.",
                "email",
                write=True,
                implemented=False,
            ),
            _tool(
                "send_email",
                "Send email",
                "Send an email through Gmail.",
                "email",
                write=True,
                implemented=False,
            ),
            _tool(
                "list_calendar_events",
                "List calendar events",
                "List Google Calendar events.",
                "calendar",
                implemented=False,
            ),
            _tool(
                "create_calendar_event",
                "Create calendar event",
                "Create a Google Calendar event.",
                "calendar",
                write=True,
                implemented=False,
            ),
            _tool(
                "update_calendar_event",
                "Update calendar event",
                "Update a Google Calendar event.",
                "calendar",
                write=True,
                implemented=False,
            ),
            _tool(
                "delete_calendar_event",
                "Delete calendar event",
                "Delete a Google Calendar event.",
                "calendar",
                write=True,
                implemented=False,
            ),
        ]
        microsoft_tools = [
            _tool(
                "search_email", "Search email", "Search Outlook mail.", "email", implemented=False
            ),
            _tool(
                "get_email_message",
                "Get email message",
                "Retrieve an Outlook message.",
                "email",
                implemented=False,
            ),
            _tool(
                "create_email_draft",
                "Create email draft",
                "Create an Outlook draft.",
                "email",
                write=True,
                implemented=False,
            ),
            _tool(
                "send_email",
                "Send email",
                "Send an email through Outlook.",
                "email",
                write=True,
                implemented=False,
            ),
            _tool(
                "list_calendar_events",
                "List calendar events",
                "List Outlook Calendar events.",
                "calendar",
                implemented=False,
            ),
            _tool(
                "create_calendar_event",
                "Create calendar event",
                "Create an Outlook event.",
                "calendar",
                write=True,
                implemented=False,
            ),
            _tool(
                "list_teams",
                "List teams",
                "List joined Microsoft Teams.",
                "teams",
                implemented=False,
            ),
            _tool(
                "list_team_channels",
                "List team channels",
                "List channels for a Team.",
                "teams",
                implemented=False,
            ),
            _tool(
                "list_channel_messages",
                "List channel messages",
                "List Teams channel messages.",
                "teams",
                implemented=False,
            ),
            _tool(
                "send_channel_message",
                "Send channel message",
                "Send a Teams channel message.",
                "teams",
                write=True,
                implemented=False,
            ),
        ]
        return [
            ProviderManifest(
                name="supabase",
                display_name="Supabase",
                status="available",
                configured=settings.supabase_oauth_configured,
                capabilities=["oauth", "projects", "database"],
                tools=supabase_tools,
            ),
            ProviderManifest(
                name="google_workspace",
                display_name="Google Workspace",
                status="planned",
                configured=settings.google_workspace_configured,
                capabilities=["oauth", "email", "calendar"],
                tools=google_tools,
            ),
            ProviderManifest(
                name="microsoft_365",
                display_name="Microsoft 365",
                status="planned",
                configured=settings.microsoft_365_configured,
                capabilities=["oauth", "email", "calendar", "teams"],
                tools=microsoft_tools,
            ),
        ]

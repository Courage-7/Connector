from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from connector_service.app import create_app
from connector_service.connectors.oauth import OAuthTokenSet
from connector_service.db.models import ProviderConnection


def _calendar_event(provider: str, title: str = "Planning") -> dict[str, object]:
    if provider == "outlook":
        return {
            "id": "event-1",
            "subject": title,
            "bodyPreview": "Quarterly planning",
            "start": {"dateTime": "2026-08-03T09:00:00+00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2026-08-03T10:00:00+00:00", "timeZone": "UTC"},
            "location": {"displayName": "Room 1"},
            "attendees": [{"emailAddress": {"address": "guest@example.com"}}],
            "webLink": "https://outlook.office.com/calendar/item/event-1",
        }
    return {
        "id": "event-1",
        "summary": title,
        "description": "Quarterly planning",
        "start": {"dateTime": "2026-08-03T09:00:00+00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2026-08-03T10:00:00+00:00", "timeZone": "UTC"},
        "location": "Room 1",
        "attendees": [{"email": "guest@example.com"}],
        "htmlLink": "https://calendar.google.com/event?eid=event-1",
    }


@pytest.mark.parametrize("provider", ["outlook", "gmail"])
def test_calendar_routes_reuse_existing_provider_connection(
    settings,
    admin_headers: dict[str, str],
    provider: str,
) -> None:
    observed: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append((request.method, request.url.path))
        collection = (
            "/v1.0/me/events" if provider == "outlook" else "/calendar/v3/calendars/primary/events"
        )
        item = f"{collection}/event-1"
        if request.url.path == collection and request.method == "GET":
            key = "value" if provider == "outlook" else "items"
            return httpx.Response(200, json={key: [_calendar_event(provider)]})
        if request.url.path == collection and request.method == "POST":
            body = json.loads(request.content)
            assert body["subject" if provider == "outlook" else "summary"] == "Planning"
            return httpx.Response(201, json=_calendar_event(provider))
        if request.url.path == item and request.method == "PATCH":
            return httpx.Response(200, json=_calendar_event(provider, "Updated planning"))
        if request.url.path == item and request.method == "DELETE":
            return httpx.Response(204)
        raise AssertionError(f"Unexpected {provider} request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    app = create_app(
        settings,
        outlook_transport=transport if provider == "outlook" else None,
        gmail_transport=transport if provider == "gmail" else None,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        project = client.post(
            "/v1/admin/projects",
            headers=admin_headers,
            json={"name": f"{provider} calendar consumer"},
        ).json()
        connection_id = _seed_connection(app, project["id"], provider)
        headers = {"X-API-Key": project["api_key"]}
        base = f"/v1/connections/{provider}/{connection_id}/calendar/events"

        listed = client.get(base, headers=headers)
        assert listed.status_code == 200, listed.text
        assert listed.json()["data"][0]["title"] == "Planning"

        created = client.post(
            base,
            headers=headers,
            json={
                "title": "Planning",
                "start": "2026-08-03T09:00:00Z",
                "end": "2026-08-03T10:00:00Z",
                "timezone": "UTC",
                "description": "Quarterly planning",
                "location": "Room 1",
                "attendees": ["guest@example.com"],
            },
        )
        assert created.status_code == 201, created.text

        updated = client.patch(
            f"{base}/event-1",
            headers=headers,
            json={"title": "Updated planning"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["title"] == "Updated planning"

        deleted = client.delete(f"{base}/event-1", headers=headers)
        assert deleted.status_code == 204, deleted.text
        assert len(observed) == 4


def test_teams_routes_list_and_send_channel_messages(settings, admin_headers) -> None:
    sent: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1.0/me/joinedTeams":
            return httpx.Response(
                200,
                json={"value": [{"id": "team-1", "displayName": "Engineering"}]},
            )
        if request.url.path == "/v1.0/teams/team-1/channels":
            return httpx.Response(
                200,
                json={"value": [{"id": "channel-1", "displayName": "General"}]},
            )
        if request.url.path == "/v1.0/teams/team-1/channels/channel-1/messages":
            if request.method == "POST":
                sent.append(json.loads(request.content))
            return httpx.Response(
                201 if request.method == "POST" else 200,
                json={
                    "value": [_team_message()] if request.method == "GET" else None,
                    **(_team_message() if request.method == "POST" else {}),
                },
            )
        raise AssertionError(f"Unexpected Teams request: {request.method} {request.url}")

    app = create_app(settings, outlook_transport=httpx.MockTransport(handler))
    with TestClient(app, raise_server_exceptions=False) as client:
        project = client.post(
            "/v1/admin/projects",
            headers=admin_headers,
            json={"name": "Teams consumer"},
        ).json()
        connection_id = _seed_connection(app, project["id"], "outlook")
        headers = {"X-API-Key": project["api_key"]}
        base = f"/v1/connections/outlook/{connection_id}/teams"

        teams = client.get(base, headers=headers)
        assert teams.status_code == 200, teams.text
        assert teams.json()[0]["name"] == "Engineering"
        channels = client.get(f"{base}/team-1/channels", headers=headers)
        assert channels.status_code == 200, channels.text
        messages_url = f"{base}/team-1/channels/channel-1/messages"
        messages = client.get(messages_url, headers=headers)
        assert messages.status_code == 200, messages.text
        assert messages.json()[0]["content"] == "Untrusted provider content"
        posted = client.post(
            messages_url,
            headers=headers,
            json={"content": "Approved project update"},
        )
        assert posted.status_code == 201, posted.text
        assert sent == [{"body": {"contentType": "text", "content": "Approved project update"}}]


def _seed_connection(app, project_id: str, provider: str) -> str:
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    tokens = OAuthTokenSet(
        access_token="provider-access-token",
        refresh_token="provider-refresh-token",
        token_type="Bearer",
        expires_at=expires_at,
    )
    connection = ProviderConnection(
        project_id=project_id,
        connector=provider,
        external_ref=f"{provider}-account",
        name=f"{provider}@example.com",
        status="active",
        encrypted_secret=app.state.credential_cipher.encrypt(tokens.secret_document()),
        token_expires_at=expires_at,
    )
    with app.state.database.session_maker() as session:
        session.add(connection)
        session.commit()
        return connection.id


def _team_message() -> dict[str, object]:
    return {
        "id": "message-1",
        "body": {"contentType": "text", "content": "Untrusted provider content"},
        "from": {"user": {"displayName": "Fixture User"}},
        "createdDateTime": "2026-08-03T09:00:00Z",
        "webUrl": "https://teams.microsoft.com/message-1",
    }

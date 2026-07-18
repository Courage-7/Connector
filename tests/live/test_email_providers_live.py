from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from connector_service.app import create_app
from connector_service.config import Settings
from connector_service.connectors.email.schemas import EmailProvider, MessageSearch
from connector_service.db.models import ProviderConnection

pytestmark = pytest.mark.live


@pytest.mark.parametrize("provider", [EmailProvider.OUTLOOK, EmailProvider.GMAIL])
def test_real_email_refresh_read_approved_send_and_sent_state(
    tmp_path: Path,
    provider: EmailProvider,
) -> None:
    live = dotenv_values(".env.email.live")
    if str(live.get("CONNECTOR_EMAIL_LIVE_SEND", "false")).lower() != "true":
        pytest.skip("Set CONNECTOR_EMAIL_LIVE_SEND=true for the explicit one-message live gate.")
    prefix = provider.value.upper()
    refresh_token = live.get(f"{prefix}_LIVE_REFRESH_TOKEN")
    sink = live.get(f"{prefix}_LIVE_SINK_ADDRESS")
    if not refresh_token or not sink:
        pytest.skip(f"{provider.value} live refresh token and controlled sink are required.")

    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / f'{provider.value}-live.db'}",
        auto_create_schema=True,
        log_level="ERROR",
    )
    if provider is EmailProvider.OUTLOOK and not settings.outlook_oauth_client_id:
        pytest.skip("Outlook OAuth client credentials are not configured in .env.")
    if provider is EmailProvider.GMAIL and not settings.gmail_oauth_client_id:
        pytest.skip("Gmail OAuth client credentials are not configured in .env.")

    app = create_app(settings)
    provider_client = app.state.providers.email_client(provider.value)
    tokens = asyncio.run(provider_client.refresh_tokens(str(refresh_token)))
    external_ref, mailbox_name = asyncio.run(provider_client.identity(tokens.access_token))
    marker = f"connector-live-{provider.value}-{uuid.uuid4().hex[:12]}"
    message = {
        "to": [str(sink)],
        "cc": [],
        "bcc": [],
        "subject": marker,
        "text_body": f"Benign Connector live acceptance message {marker}.",
        "html_body": None,
    }

    with TestClient(app, raise_server_exceptions=False) as client:
        project_response = client.post(
            "/v1/admin/projects",
            headers={"X-Admin-Token": settings.admin_token.get_secret_value()},
            json={"name": f"Live {provider.value} acceptance"},
        )
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()
        with app.state.database.session_maker() as session:
            connection = ProviderConnection(
                project_id=project["id"],
                connector=provider.value,
                external_ref=external_ref,
                name=mailbox_name,
                status="active",
                encrypted_secret=app.state.credential_cipher.encrypt(tokens.secret_document()),
                token_expires_at=tokens.expires_at,
            )
            session.add(connection)
            session.commit()
            connection_id = connection.id

        headers = {"X-API-Key": project["api_key"]}
        folders = client.get(
            f"/v1/connections/{provider.value}/{connection_id}/folders",
            headers=headers,
        )
        assert folders.status_code == 200, folders.text
        assert folders.json()

        requested = client.post(
            (f"/v1/agent/connections/{provider.value}/{connection_id}/email-send-requests"),
            headers=headers,
            json=message,
        )
        assert requested.status_code == 200, requested.text
        request_id = requested.json()["id"]
        csrf = _dashboard_session(client, project["api_key"])
        approved = client.post(
            f"/v1/dashboard/email-send-requests/{request_id}/approve",
            headers={"X-CSRF-Token": csrf},
            json={"note": "Live controlled-sink acceptance."},
        )
        assert approved.status_code == 200, approved.text
        executed = client.post(
            f"/v1/agent/email-send-requests/{request_id}/execute",
            headers=headers,
        )
        assert executed.status_code == 200, executed.text
        assert executed.json()["status"] == "executed"
        replay = client.post(
            f"/v1/agent/email-send-requests/{request_id}/execute",
            headers=headers,
        )
        assert replay.status_code == 409

        sent_folder = "sentitems" if provider is EmailProvider.OUTLOOK else "SENT"
        found = False
        for _ in range(6):
            result = asyncio.run(
                provider_client.search_messages(
                    tokens.access_token,
                    MessageSearch(query=marker, folder_id=sent_folder, limit=10),
                )
            )
            if any(item.subject == marker for item in result.data):
                found = True
                break
            time.sleep(2)
        assert found, "The accepted message did not appear in the provider Sent folder."

        audit = client.get("/v1/dashboard/email-audit")
        assert audit.status_code == 200, audit.text
        assert audit.json()[0]["status"] == "succeeded"
        assert marker not in audit.text
        assert str(sink) not in audit.text


def _dashboard_session(client: TestClient, api_key: str) -> str:
    ticket = client.post(
        "/v1/dashboard/login-tickets",
        headers={"X-API-Key": api_key},
        json={"return_to": "/app/"},
    )
    assert ticket.status_code == 200, ticket.text
    exchange = client.get(ticket.json()["login_url"], follow_redirects=False)
    assert exchange.status_code == 303, exchange.text
    csrf = client.cookies.get("connector_dashboard_csrf")
    assert csrf
    return csrf

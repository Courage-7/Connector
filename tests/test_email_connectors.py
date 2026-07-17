from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from connector_service.app import create_app
from connector_service.db.models import EmailAuditRecord, EmailSendRequest, ProviderConnection


def _consumer(client: TestClient, admin_headers: dict[str, str], provider: str) -> dict[str, str]:
    response = client.post(
        "/v1/admin/projects",
        headers=admin_headers,
        json={"name": f"{provider.title()} consumer"},
    )
    assert response.status_code == 201, response.text
    return response.json()


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


def _outlook_message() -> dict[str, object]:
    return {
        "id": "outlook-message-1",
        "conversationId": "thread-1",
        "subject": "Mailbox fixture",
        "from": {
            "emailAddress": {
                "address": "sender@example.com",
                "name": "Fixture Sender",
            }
        },
        "toRecipients": [{"emailAddress": {"address": "outlook-fixture@example.com"}}],
        "ccRecipients": [],
        "bccRecipients": [],
        "receivedDateTime": "2026-07-17T09:30:00Z",
        "bodyPreview": "Untrusted fixture preview",
        "body": {"contentType": "text", "content": "Untrusted fixture body"},
        "hasAttachments": True,
        "isRead": False,
    }


def _gmail_message() -> dict[str, object]:
    body = base64.urlsafe_b64encode(b"Untrusted fixture body").decode().rstrip("=")
    return {
        "id": "gmail-message-1",
        "threadId": "thread-1",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "Untrusted fixture preview",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "Subject", "value": "Mailbox fixture"},
                {"name": "From", "value": "Fixture Sender <sender@example.com>"},
                {"name": "To", "value": "gmail-fixture@example.com"},
                {"name": "Date", "value": "Fri, 17 Jul 2026 09:30:00 +0000"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": body}},
                {
                    "filename": "fixture.pdf",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "gmail-attachment-1", "size": 128},
                },
            ],
        },
    }


@pytest.mark.parametrize("provider", ["outlook", "gmail"])
def test_email_oauth_send_is_exactly_approved_once_and_redacted(
    settings,
    admin_headers: dict[str, str],
    provider: str,
) -> None:
    sent_messages: list[dict[str, object]] = []

    def outlook_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            form = parse_qs(request.content.decode())
            assert form["code_verifier"] == [form["code_verifier"][0]]
            return httpx.Response(
                200,
                json={
                    "access_token": "outlook-access",
                    "refresh_token": "outlook-refresh",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "Mail.ReadWrite Mail.Send offline_access",
                },
            )
        if request.url.path == "/v1.0/me":
            return httpx.Response(
                200,
                json={
                    "id": "outlook-account-id",
                    "displayName": "Outlook Fixture",
                    "mail": "outlook-fixture@example.com",
                },
            )
        if request.url.path == "/v1.0/me/mailFolders":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "inbox",
                            "displayName": "Inbox",
                            "unreadItemCount": 2,
                            "totalItemCount": 8,
                        }
                    ]
                },
            )
        if request.url.path == "/v1.0/me/messages" and request.method == "GET":
            return httpx.Response(200, json={"value": [_outlook_message()]})
        if request.url.path == "/v1.0/me/messages/outlook-message-1":
            return httpx.Response(200, json=_outlook_message())
        if request.url.path == "/v1.0/me/messages/outlook-message-1/attachments":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "outlook-attachment-1",
                            "name": "fixture.pdf",
                            "contentType": "application/pdf",
                            "size": 128,
                            "isInline": False,
                        }
                    ]
                },
            )
        if request.url.path == "/v1.0/me/messages" and request.method == "POST":
            return httpx.Response(201, json={"id": "outlook-draft-1"})
        if request.url.path == "/v1.0/me/sendMail":
            sent_messages.append(json.loads(request.content))
            return httpx.Response(202)
        raise AssertionError(f"Unexpected Outlook request: {request.method} {request.url}")

    def gmail_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "gmail-access",
                    "refresh_token": "gmail-refresh",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "openid email https://www.googleapis.com/auth/gmail.compose",
                },
            )
        if request.url.path == "/v1/userinfo":
            return httpx.Response(
                200,
                json={"sub": "google-account-id", "email": "gmail-fixture@example.com"},
            )
        if request.url.path == "/gmail/v1/users/me/labels":
            return httpx.Response(
                200,
                json={
                    "labels": [
                        {
                            "id": "INBOX",
                            "name": "Inbox",
                            "messagesUnread": 2,
                            "messagesTotal": 8,
                        }
                    ]
                },
            )
        if request.url.path == "/gmail/v1/users/me/messages":
            return httpx.Response(200, json={"messages": [{"id": "gmail-message-1"}]})
        if request.url.path == "/gmail/v1/users/me/messages/gmail-message-1":
            return httpx.Response(200, json=_gmail_message())
        if request.url.path == "/gmail/v1/users/me/threads/thread-1":
            return httpx.Response(200, json={"messages": [_gmail_message()]})
        if request.url.path == "/gmail/v1/users/me/drafts":
            return httpx.Response(200, json={"id": "gmail-draft-1"})
        if request.url.path == "/gmail/v1/users/me/messages/send":
            sent_messages.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "sent-message", "threadId": "thread-1"})
        if request.url.path == "/revoke":
            return httpx.Response(200)
        raise AssertionError(f"Unexpected Gmail request: {request.method} {request.url}")

    configured = settings.model_copy(
        update={
            "outlook_oauth_client_id": "outlook-client",
            "outlook_oauth_client_secret": SecretStr("outlook-client-secret"),
            "gmail_oauth_client_id": "gmail-client",
            "gmail_oauth_client_secret": SecretStr("gmail-client-secret"),
        }
    )
    app = create_app(
        configured,
        outlook_transport=httpx.MockTransport(outlook_handler),
        gmail_transport=httpx.MockTransport(gmail_handler),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        consumer = _consumer(client, admin_headers, provider)
        headers = {"X-API-Key": consumer["api_key"]}
        started = client.post(
            f"/v1/connections/{provider}/authorize",
            headers=headers,
            json={},
        )
        assert started.status_code == 200, started.text
        authorization_url = started.json()["authorization_url"]
        parameters = parse_qs(urlparse(authorization_url).query)
        assert parameters["code_challenge_method"] == ["S256"]
        assert "state" in parameters
        callback = client.get(
            f"/v1/connections/{provider}/callback",
            params={"code": "provider-code", "state": parameters["state"][0]},
        )
        assert callback.status_code == 200, callback.text
        connection = callback.json()["connection"]
        assert connection["status"] == "active"
        assert connection["connector"] == provider

        listed = client.get(f"/v1/connections/{provider}", headers=headers)
        assert listed.status_code == 200, listed.text
        assert listed.json()[0]["id"] == connection["id"]
        folders = client.get(
            f"/v1/connections/{provider}/{connection['id']}/folders",
            headers=headers,
        )
        assert folders.status_code == 200, folders.text
        assert folders.json()[0]["name"] == "Inbox"
        search = client.post(
            f"/v1/connections/{provider}/{connection['id']}/messages/search",
            headers=headers,
            json={"query": "fixture", "folder_id": None, "limit": 10},
        )
        assert search.status_code == 200, search.text
        assert search.json()["returned"] == 1
        message_id = f"{provider}-message-1"
        message_detail = client.get(
            f"/v1/connections/{provider}/{connection['id']}/messages/{message_id}",
            headers=headers,
        )
        assert message_detail.status_code == 200, message_detail.text
        assert message_detail.json()["body"]["content"] == "Untrusted fixture body"
        thread = client.get(
            f"/v1/connections/{provider}/{connection['id']}/threads/thread-1",
            headers=headers,
        )
        assert thread.status_code == 200, thread.text
        assert len(thread.json()["messages"]) == 1
        attachments = client.get(
            f"/v1/connections/{provider}/{connection['id']}/messages/{message_id}/attachments",
            headers=headers,
        )
        assert attachments.status_code == 200, attachments.text
        assert attachments.json()[0]["name"] == "fixture.pdf"
        draft = client.post(
            f"/v1/connections/{provider}/{connection['id']}/drafts",
            headers=headers,
            json={
                "to": ["controlled-sink@example.com"],
                "subject": "Draft fixture",
                "text_body": "Exact draft body.",
            },
        )
        assert draft.status_code == 200, draft.text
        assert draft.json()["provider"] == provider

        replay = client.get(
            f"/v1/connections/{provider}/callback",
            params={"code": "provider-code", "state": parameters["state"][0]},
        )
        assert replay.status_code == 422

        message = {
            "to": ["controlled-sink@example.com"],
            "cc": [],
            "bcc": [],
            "subject": f"Connector {provider} acceptance fixture",
            "text_body": "Benign exact body for approval.",
            "html_body": None,
        }
        requested = client.post(
            f"/v1/agent/connections/{provider}/{connection['id']}/email-send-requests",
            headers=headers,
            json=message,
        )
        assert requested.status_code == 200, requested.text
        send_request_id = requested.json()["id"]
        assert requested.json()["status"] == "pending"
        assert sent_messages == []

        with app.state.database.session_maker() as session:
            stored = session.scalar(
                select(EmailSendRequest).where(EmailSendRequest.id == send_request_id)
            )
            assert stored is not None
            assert b"controlled-sink@example.com" not in stored.encrypted_message
            assert b"Benign exact body" not in stored.encrypted_message
            assert len(stored.payload_digest) == 32

        blocked = client.post(
            f"/v1/agent/email-send-requests/{send_request_id}/execute",
            headers=headers,
        )
        assert blocked.status_code == 409

        csrf = _dashboard_session(client, consumer["api_key"])
        pending = client.get("/v1/dashboard/email-send-requests?status=pending")
        assert pending.status_code == 200, pending.text
        assert pending.json()[0]["message"]["text_body"] == message["text_body"]
        approved = client.post(
            f"/v1/dashboard/email-send-requests/{send_request_id}/approve",
            headers={"X-CSRF-Token": csrf},
            json={"note": "Exact content reviewed."},
        )
        assert approved.status_code == 200, approved.text

        executed = client.post(
            f"/v1/agent/email-send-requests/{send_request_id}/execute",
            headers=headers,
        )
        assert executed.status_code == 200, executed.text
        assert executed.json()["status"] == "executed"
        assert len(sent_messages) == 1

        replay_send = client.post(
            f"/v1/agent/email-send-requests/{send_request_id}/execute",
            headers=headers,
        )
        assert replay_send.status_code == 409
        assert len(sent_messages) == 1

        audit = client.get("/v1/dashboard/email-audit")
        assert audit.status_code == 200, audit.text
        assert audit.json()[0]["action"] == "send_message"
        assert audit.json()[0]["recipient_count"] == 1
        assert "controlled-sink@example.com" not in audit.text
        assert "Benign exact body" not in audit.text

        bcc = client.post(
            f"/v1/agent/connections/{provider}/{connection['id']}/email-send-requests",
            headers=headers,
            json={**message, "bcc": ["hidden@example.com"]},
        )
        assert bcc.status_code == 403

        disconnected = client.delete(
            f"/v1/connections/{provider}/{connection['id']}",
            headers=headers,
        )
        assert disconnected.status_code == 204, disconnected.text
        inactive = client.get(
            f"/v1/connections/{provider}/{connection['id']}/folders",
            headers=headers,
        )
        assert inactive.status_code == 404


def test_email_routes_refresh_tokens_and_redact_provider_failures(
    settings,
    admin_headers: dict[str, str],
) -> None:
    token_grants: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            form = parse_qs(request.content.decode())
            grant = form["grant_type"][0]
            token_grants.append(grant)
            if grant == "authorization_code":
                assert form["code_verifier"][0]
                return httpx.Response(
                    200,
                    json={
                        "access_token": "expired-access",
                        "refresh_token": "stable-refresh",
                        "expires_in": 1,
                    },
                )
            assert form["refresh_token"] == ["stable-refresh"]
            return httpx.Response(
                200,
                json={"access_token": "refreshed-access", "expires_in": 3600},
            )
        if request.url.path == "/v1.0/me":
            return httpx.Response(
                200,
                json={"id": "failing-account-id", "mail": "failures@example.com"},
            )
        assert request.headers["Authorization"] == "Bearer refreshed-access"
        return httpx.Response(503, json={"error": {"code": "serviceUnavailable"}})

    configured = settings.model_copy(
        update={
            "outlook_oauth_client_id": "outlook-client",
            "outlook_oauth_client_secret": SecretStr("outlook-client-secret"),
        }
    )
    app = create_app(configured, outlook_transport=httpx.MockTransport(handler))
    with TestClient(app, raise_server_exceptions=False) as client:
        consumer = _consumer(client, admin_headers, "outlook-failures")
        headers = {"X-API-Key": consumer["api_key"]}
        denied = client.get(
            "/v1/connections/outlook/callback",
            params={"error": "access_denied", "state": "rejected-state"},
        )
        assert denied.status_code == 422
        started = client.post(
            "/v1/connections/outlook/authorize",
            headers=headers,
            json={"login_hint": "failures@example.com"},
        )
        state = parse_qs(urlparse(started.json()["authorization_url"]).query)["state"][0]
        callback = client.get(
            "/v1/connections/outlook/callback",
            params={"code": "provider-code", "state": state},
        )
        assert callback.status_code == 200, callback.text
        connection_id = callback.json()["connection"]["id"]

        requests = [
            ("get", f"/v1/connections/outlook/{connection_id}/folders", None),
            (
                "post",
                f"/v1/connections/outlook/{connection_id}/messages/search",
                {"query": "fixture", "limit": 5},
            ),
            (
                "get",
                f"/v1/connections/outlook/{connection_id}/messages/message-1",
                None,
            ),
            ("get", f"/v1/connections/outlook/{connection_id}/threads/thread-1", None),
            (
                "get",
                f"/v1/connections/outlook/{connection_id}/messages/message-1/attachments",
                None,
            ),
            (
                "post",
                f"/v1/connections/outlook/{connection_id}/drafts",
                {
                    "to": ["controlled-sink@example.com"],
                    "subject": "Failure fixture",
                    "text_body": "Exact failure fixture body.",
                },
            ),
        ]
        for method, url, payload in requests:
            response = client.request(method, url, headers=headers, json=payload)
            assert response.status_code == 503, response.text
            assert "serviceUnavailable" not in response.text

        assert token_grants == ["authorization_code", "refresh_token"]
        with app.state.database.session_maker() as session:
            connection = session.scalar(
                select(ProviderConnection).where(ProviderConnection.id == connection_id)
            )
            assert connection is not None
            secret = app.state.credential_cipher.decrypt(connection.encrypted_secret)
            assert secret["access_token"] == "refreshed-access"
            assert secret["refresh_token"] == "stable-refresh"
            audit = session.scalars(select(EmailAuditRecord)).all()
            assert len(audit) == len(requests)
            assert all(item.status == "failed" for item in audit)
            assert all(item.error_code == "provider_unavailable" for item in audit)

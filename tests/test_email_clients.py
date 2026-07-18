from __future__ import annotations

import asyncio
import base64
import json

import httpx
from pydantic import SecretStr

from connector_service.connectors.email.schemas import EmailCompose, MessageSearch
from connector_service.providers.gmail.client import GmailClient
from connector_service.providers.outlook.client import OutlookClient


def test_outlook_read_search_attachments_and_draft(settings) -> None:
    observed: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append((request.method, request.url.path))
        if request.url.path == "/v1.0/me/mailFolders":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "inbox",
                            "displayName": "Inbox",
                            "unreadItemCount": 2,
                            "totalItemCount": 10,
                        }
                    ]
                },
            )
        if request.url.path == "/v1.0/me/messages" and request.method == "GET":
            assert request.url.params["$search"] == '"subject:fixture"'
            return httpx.Response(200, json={"value": [_outlook_message()]})
        if request.url.path == "/v1.0/me/messages/message-1":
            return httpx.Response(200, json=_outlook_message(body=True))
        if request.url.path == "/v1.0/me/messages/message-1/attachments":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "attachment-1",
                            "name": "fixture.txt",
                            "contentType": "text/plain",
                            "size": 12,
                            "isInline": False,
                        }
                    ]
                },
            )
        if request.url.path == "/v1.0/me/messages" and request.method == "POST":
            assert json.loads(request.content)["toRecipients"][0]["emailAddress"]["address"]
            return httpx.Response(201, json={"id": "draft-1"})
        raise AssertionError(f"Unexpected Outlook request: {request.method} {request.url}")

    client = OutlookClient(
        settings.model_copy(
            update={
                "outlook_oauth_client_id": "client",
                "outlook_oauth_client_secret": SecretStr("secret"),
            }
        ),
        transport=httpx.MockTransport(handler),
    )
    folders = asyncio.run(client.list_folders("access"))
    assert folders[0].name == "Inbox"
    page = asyncio.run(
        client.search_messages("access", MessageSearch(query="subject:fixture", limit=10))
    )
    assert page.data[0].subject == "Fixture message"
    message = asyncio.run(client.get_message("access", "message-1"))
    assert message.body is not None
    assert message.body.content == "Untrusted fixture body"
    attachments = asyncio.run(client.list_attachments("access", "message-1"))
    assert attachments[0].name == "fixture.txt"
    draft = asyncio.run(client.create_draft("access", _compose()))
    assert draft.id == "draft-1"
    assert observed[-1] == ("POST", "/v1.0/me/messages")


def test_gmail_search_parses_mime_and_creates_rfc2822_draft(settings) -> None:
    observed_raw: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/gmail/v1/users/me/messages":
            assert request.url.params["q"] == "subject:fixture"
            return httpx.Response(200, json={"messages": [{"id": "message-1"}]})
        if request.url.path == "/gmail/v1/users/me/messages/message-1":
            return httpx.Response(200, json=_gmail_message())
        if request.url.path == "/gmail/v1/users/me/drafts":
            raw = json.loads(request.content)["message"]["raw"]
            observed_raw.append(raw)
            return httpx.Response(200, json={"id": "draft-1"})
        raise AssertionError(f"Unexpected Gmail request: {request.method} {request.url}")

    client = GmailClient(
        settings.model_copy(
            update={
                "gmail_oauth_client_id": "client",
                "gmail_oauth_client_secret": SecretStr("secret"),
            }
        ),
        transport=httpx.MockTransport(handler),
    )
    page = asyncio.run(
        client.search_messages("access", MessageSearch(query="subject:fixture", limit=10))
    )
    assert page.data[0].subject == "Fixture message"
    detail = asyncio.run(client.get_message("access", "message-1"))
    assert detail.body is not None
    assert detail.body.content == "Untrusted fixture body"
    assert asyncio.run(client.list_attachments("access", "message-1"))[0].name == "fixture.txt"
    draft = asyncio.run(client.create_draft("access", _compose()))
    assert draft.id == "draft-1"
    decoded = base64.urlsafe_b64decode(observed_raw[0] + "=" * (-len(observed_raw[0]) % 4))
    assert b"To: controlled-sink@example.com" in decoded
    assert b"Subject: Approved fixture" in decoded


def _compose() -> EmailCompose:
    return EmailCompose(
        to=["controlled-sink@example.com"],
        cc=[],
        bcc=[],
        subject="Approved fixture",
        text_body="Benign content",
    )


def _outlook_message(*, body: bool = False) -> dict[str, object]:
    result: dict[str, object] = {
        "id": "message-1",
        "conversationId": "conversation-1",
        "subject": "Fixture message",
        "from": {"emailAddress": {"address": "sender@example.com", "name": "Sender"}},
        "toRecipients": [{"emailAddress": {"address": "reader@example.com"}}],
        "receivedDateTime": "2026-07-17T08:00:00Z",
        "bodyPreview": "Untrusted fixture body",
        "hasAttachments": True,
        "isRead": False,
    }
    if body:
        result["body"] = {"contentType": "text", "content": "Untrusted fixture body"}
    return result


def _gmail_message() -> dict[str, object]:
    body = base64.urlsafe_b64encode(b"Untrusted fixture body").decode().rstrip("=")
    return {
        "id": "message-1",
        "threadId": "thread-1",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "Untrusted fixture body",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "Subject", "value": "Fixture message"},
                {"name": "From", "value": "Sender <sender@example.com>"},
                {"name": "To", "value": "reader@example.com"},
                {"name": "Date", "value": "Fri, 17 Jul 2026 08:00:00 +0000"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": body, "size": 22}},
                {
                    "mimeType": "text/plain",
                    "filename": "fixture.txt",
                    "body": {"attachmentId": "attachment-1", "size": 12},
                },
            ],
        },
    }

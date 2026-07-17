"""Microsoft Graph OAuth and delegated Outlook Mail client."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from connector_service.config import Settings
from connector_service.connectors.email.base import DefensiveProviderClient, identity
from connector_service.connectors.email.schemas import (
    AttachmentMetadata,
    DraftResponse,
    EmailCompose,
    EmailIdentity,
    EmailProvider,
    MailFolder,
    MessageBody,
    MessageDetail,
    MessagePage,
    MessageSearch,
    MessageSummary,
    MessageThread,
)
from connector_service.connectors.oauth import OAuthTokenSet
from connector_service.core.exceptions import InvalidRequestError, ProviderRequestError

OUTLOOK_SCOPES = (
    "openid",
    "profile",
    "email",
    "offline_access",
    "User.Read",
    "Mail.ReadWrite",
    "Mail.Send",
)
MESSAGE_SELECT = (
    "id,conversationId,subject,from,toRecipients,ccRecipients,bccRecipients,"
    "receivedDateTime,bodyPreview,body,hasAttachments,isRead"
)


class OutlookClient(DefensiveProviderClient):
    provider = "Outlook"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            settings,
            api_base_url=settings.outlook_graph_api_url,
            transport=transport,
        )

    def authorization_url(
        self,
        *,
        state: str,
        code_challenge: str,
        login_hint: str | None,
    ) -> str:
        client_id, _ = self._oauth_credentials()
        parameters = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": self._settings.outlook_oauth_redirect_uri,
            "response_mode": "query",
            "scope": " ".join(OUTLOOK_SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        if login_hint:
            parameters["login_hint"] = login_hint
        return f"{self._settings.outlook_oauth_authority}/authorize?{urlencode(parameters)}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> OAuthTokenSet:
        payload = await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._settings.outlook_oauth_redirect_uri,
                "code_verifier": code_verifier,
            }
        )
        return OAuthTokenSet.from_response(payload, provider=self.provider)

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokenSet:
        payload = await self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": " ".join(OUTLOOK_SCOPES),
            }
        )
        return OAuthTokenSet.from_response(
            payload,
            provider=self.provider,
            fallback_refresh_token=refresh_token,
        )

    async def revoke(self, token: str) -> None:
        # Microsoft identity does not expose an OAuth token-revocation endpoint for this flow.
        # Deleting the encrypted local token is the deterministic disconnect operation.
        del token

    async def identity(self, access_token: str) -> tuple[str, str]:
        payload = await self._request_json(
            "GET",
            "/me",
            access_token=access_token,
            params={"$select": "id,displayName,mail,userPrincipalName"},
        )
        if not isinstance(payload, dict):
            raise ProviderRequestError("Outlook returned an invalid profile.")
        external_ref = payload.get("id")
        address = payload.get("mail") or payload.get("userPrincipalName")
        if not isinstance(external_ref, str) or not external_ref or not isinstance(address, str):
            raise ProviderRequestError("Outlook returned an invalid profile.")
        return external_ref, address

    async def list_folders(self, access_token: str) -> list[MailFolder]:
        payload = await self._request_json(
            "GET",
            "/me/mailFolders",
            access_token=access_token,
            params={"$top": 100, "$select": "id,displayName,unreadItemCount,totalItemCount"},
        )
        values = _values(payload)
        return [
            MailFolder(
                id=_required_string(item, "id"),
                name=_required_string(item, "displayName"),
                unread_count=_optional_int(item.get("unreadItemCount")),
                total_count=_optional_int(item.get("totalItemCount")),
            )
            for item in values
        ]

    async def search_messages(
        self,
        access_token: str,
        request: MessageSearch,
    ) -> MessagePage:
        if request.folder_id:
            path = f"/me/mailFolders/{quote(request.folder_id, safe='')}/messages"
        else:
            path = "/me/messages"
        params: dict[str, Any] = {"$top": request.limit, "$select": MESSAGE_SELECT}
        headers: dict[str, str] = {"Prefer": 'outlook.body-content-type="text"'}
        if request.query:
            escaped = request.query.replace('"', '\\"')
            params["$search"] = f'"{escaped}"'
            headers["ConsistencyLevel"] = "eventual"
        else:
            params["$orderby"] = "receivedDateTime desc"
        payload = await self._request_json(
            "GET",
            path,
            access_token=access_token,
            params=params,
            headers=headers,
        )
        rows = [_summary(item) for item in _values(payload)[: request.limit]]
        return MessagePage(data=rows, returned=len(rows))

    async def get_message(self, access_token: str, message_id: str) -> MessageDetail:
        payload = await self._request_json(
            "GET",
            f"/me/messages/{quote(message_id, safe='')}",
            access_token=access_token,
            params={"$select": MESSAGE_SELECT},
            headers={"Prefer": 'outlook.body-content-type="text"'},
        )
        if not isinstance(payload, dict):
            raise ProviderRequestError("Outlook returned an invalid message.")
        return _detail(payload)

    async def get_thread(self, access_token: str, thread_id: str) -> MessageThread:
        escaped = thread_id.replace("'", "''")
        payload = await self._request_json(
            "GET",
            "/me/messages",
            access_token=access_token,
            params={
                "$filter": f"conversationId eq '{escaped}'",
                "$orderby": "receivedDateTime asc",
                "$top": 50,
                "$select": MESSAGE_SELECT,
            },
            headers={"Prefer": 'outlook.body-content-type="text"'},
        )
        return MessageThread(id=thread_id, messages=[_detail(item) for item in _values(payload)])

    async def list_attachments(
        self,
        access_token: str,
        message_id: str,
    ) -> list[AttachmentMetadata]:
        payload = await self._request_json(
            "GET",
            f"/me/messages/{quote(message_id, safe='')}/attachments",
            access_token=access_token,
            params={"$top": 100, "$select": "id,name,contentType,size,isInline"},
        )
        return [
            AttachmentMetadata(
                id=_required_string(item, "id"),
                name=_required_string(item, "name"),
                content_type=_optional_string(item.get("contentType")),
                size=_optional_int(item.get("size")),
                inline=bool(item.get("isInline", False)),
            )
            for item in _values(payload)
        ]

    async def create_draft(self, access_token: str, message: EmailCompose) -> DraftResponse:
        payload = await self._request_json(
            "POST",
            "/me/messages",
            access_token=access_token,
            json_body=_graph_message(message),
        )
        if not isinstance(payload, dict):
            raise ProviderRequestError("Outlook returned an invalid draft.")
        draft_id = _required_string(payload, "id")
        return DraftResponse(
            id=draft_id,
            provider=EmailProvider.OUTLOOK,
            subject=message.subject,
            recipient_count=len(message.to + message.cc + message.bcc),
        )

    async def send_message(self, access_token: str, message: EmailCompose) -> None:
        await self._request(
            "POST",
            "/me/sendMail",
            access_token=access_token,
            json_body={"message": _graph_message(message), "saveToSentItems": True},
        )

    async def _token_request(self, form: dict[str, str]) -> Any:
        client_id, client_secret = self._oauth_credentials()
        return await self._request_json(
            "POST",
            "/token",
            form={**form, "client_id": client_id, "client_secret": client_secret},
            base_url=self._settings.outlook_oauth_authority,
        )

    def _oauth_credentials(self) -> tuple[str, str]:
        client_id = self._settings.outlook_oauth_client_id
        client_secret = self._settings.outlook_oauth_client_secret
        if not client_id or client_secret is None:
            raise InvalidRequestError("Outlook OAuth is not configured for this connector service.")
        return client_id, client_secret.get_secret_value()


def _graph_message(message: EmailCompose) -> dict[str, Any]:
    content_type = "HTML" if message.html_body else "Text"
    content = message.html_body or message.text_body or ""
    return {
        "subject": message.subject,
        "body": {"contentType": content_type, "content": content},
        "toRecipients": _graph_recipients(message.to),
        "ccRecipients": _graph_recipients(message.cc),
        "bccRecipients": _graph_recipients(message.bcc),
    }


def _graph_recipients(addresses: list[str]) -> list[dict[str, dict[str, str]]]:
    return [{"emailAddress": {"address": address}} for address in addresses]


def _summary(payload: dict[str, Any]) -> MessageSummary:
    received_at = _datetime(payload.get("receivedDateTime"))
    sender_payload = payload.get("from")
    sender = _recipient(sender_payload) if isinstance(sender_payload, dict) else None
    return MessageSummary(
        id=_required_string(payload, "id"),
        thread_id=_optional_string(payload.get("conversationId")),
        subject=_optional_string(payload.get("subject")) or "(no subject)",
        sender=sender,
        recipients=_recipients(payload.get("toRecipients")),
        received_at=received_at,
        snippet=(_optional_string(payload.get("bodyPreview")) or "")[:1000],
        has_attachments=bool(payload.get("hasAttachments", False)),
        is_read=payload.get("isRead") if isinstance(payload.get("isRead"), bool) else None,
    )


def _detail(payload: dict[str, Any]) -> MessageDetail:
    summary = _summary(payload)
    body = payload.get("body")
    message_body = None
    if isinstance(body, dict):
        content = body.get("content")
        content_type = body.get("contentType")
        if isinstance(content, str) and isinstance(content_type, str):
            message_body = MessageBody(content_type=content_type.lower(), content=content)
    return MessageDetail(
        **summary.model_dump(),
        cc_recipients=_recipients(payload.get("ccRecipients")),
        bcc_recipients=_recipients(payload.get("bccRecipients")),
        body=message_body,
    )


def _recipients(value: Any) -> list[EmailIdentity]:
    if not isinstance(value, list):
        return []
    recipients: list[EmailIdentity] = []
    for item in value:
        if isinstance(item, dict) and (recipient := _recipient(item)) is not None:
            recipients.append(recipient)
    return recipients


def _recipient(value: dict[str, Any]) -> EmailIdentity | None:
    email_address = value.get("emailAddress")
    if not isinstance(email_address, dict):
        return None
    address = email_address.get("address")
    name = email_address.get("name")
    if not isinstance(address, str):
        return None
    return identity(address, name if isinstance(name, str) else None)


def _values(payload: Any) -> list[dict[str, Any]]:
    values = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise ProviderRequestError("Outlook returned an invalid collection.")
    return values


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ProviderRequestError("Outlook returned an invalid object.")
    return value


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

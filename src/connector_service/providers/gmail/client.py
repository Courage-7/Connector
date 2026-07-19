"""Google OAuth and delegated Gmail REST client."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
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
from connector_service.connectors.productivity.schemas import (
    CalendarEvent,
    CalendarEventCreate,
    CalendarEventPage,
    CalendarEventUpdate,
)
from connector_service.core.exceptions import InvalidRequestError, ProviderRequestError

GMAIL_SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.events",
)
METADATA_HEADERS = ["Subject", "From", "To", "Cc", "Bcc", "Date"]


class GmailClient(DefensiveProviderClient):
    provider = "Gmail"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(settings, api_base_url=settings.gmail_api_url, transport=transport)

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
            "redirect_uri": self._settings.gmail_oauth_redirect_uri,
            "scope": " ".join(GMAIL_SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
        }
        if login_hint:
            parameters["login_hint"] = login_hint
        return f"{self._settings.gmail_oauth_authority}/auth?{urlencode(parameters)}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> OAuthTokenSet:
        payload = await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._settings.gmail_oauth_redirect_uri,
                "code_verifier": code_verifier,
            }
        )
        return OAuthTokenSet.from_response(payload, provider=self.provider)

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokenSet:
        payload = await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )
        return OAuthTokenSet.from_response(
            payload,
            provider=self.provider,
            fallback_refresh_token=refresh_token,
        )

    async def revoke(self, token: str) -> None:
        await self._request(
            "POST",
            "/revoke",
            form={"token": token},
            base_url=self._settings.gmail_token_url,
        )

    async def identity(self, access_token: str) -> tuple[str, str]:
        payload = await self._request_json(
            "GET",
            "/userinfo",
            access_token=access_token,
            base_url=self._settings.gmail_userinfo_url,
        )
        subject = payload.get("sub") if isinstance(payload, dict) else None
        address = payload.get("email") if isinstance(payload, dict) else None
        if (
            not isinstance(subject, str)
            or not subject
            or not isinstance(address, str)
            or not address
        ):
            raise ProviderRequestError("Gmail returned an invalid profile.")
        return subject, address.lower()

    async def list_folders(self, access_token: str) -> list[MailFolder]:
        payload = await self._request_json(
            "GET",
            "/users/me/labels",
            access_token=access_token,
        )
        labels = payload.get("labels") if isinstance(payload, dict) else None
        if not isinstance(labels, list) or any(not isinstance(item, dict) for item in labels):
            raise ProviderRequestError("Gmail returned an invalid label collection.")
        return [
            MailFolder(
                id=_required_string(item, "id"),
                name=_required_string(item, "name"),
                unread_count=_optional_int(item.get("messagesUnread")),
                total_count=_optional_int(item.get("messagesTotal")),
            )
            for item in labels
        ]

    async def search_messages(
        self,
        access_token: str,
        request: MessageSearch,
    ) -> MessagePage:
        params: dict[str, Any] = {"maxResults": request.limit}
        if request.query:
            params["q"] = request.query
        if request.folder_id:
            params["labelIds"] = request.folder_id
        payload = await self._request_json(
            "GET",
            "/users/me/messages",
            access_token=access_token,
            params=params,
        )
        references = payload.get("messages", []) if isinstance(payload, dict) else None
        if not isinstance(references, list) or any(
            not isinstance(item, dict) for item in references
        ):
            raise ProviderRequestError("Gmail returned an invalid message collection.")
        rows: list[MessageSummary] = []
        for reference in references[: request.limit]:
            message_id = _required_string(reference, "id")
            item = await self._request_json(
                "GET",
                f"/users/me/messages/{quote(message_id, safe='')}",
                access_token=access_token,
                params=[
                    ("format", "metadata"),
                    *(("metadataHeaders", header) for header in METADATA_HEADERS),
                ],
            )
            rows.append(_summary(item))
        return MessagePage(data=rows, returned=len(rows))

    async def get_message(self, access_token: str, message_id: str) -> MessageDetail:
        payload = await self._request_json(
            "GET",
            f"/users/me/messages/{quote(message_id, safe='')}",
            access_token=access_token,
            params={"format": "full"},
        )
        if not isinstance(payload, dict):
            raise ProviderRequestError("Gmail returned an invalid message.")
        return _detail(payload)

    async def get_thread(self, access_token: str, thread_id: str) -> MessageThread:
        payload = await self._request_json(
            "GET",
            f"/users/me/threads/{quote(thread_id, safe='')}",
            access_token=access_token,
            params={"format": "full"},
        )
        messages = payload.get("messages") if isinstance(payload, dict) else None
        if not isinstance(messages, list) or any(not isinstance(item, dict) for item in messages):
            raise ProviderRequestError("Gmail returned an invalid thread.")
        return MessageThread(id=thread_id, messages=[_detail(item) for item in messages])

    async def list_attachments(
        self,
        access_token: str,
        message_id: str,
    ) -> list[AttachmentMetadata]:
        payload = await self._request_json(
            "GET",
            f"/users/me/messages/{quote(message_id, safe='')}",
            access_token=access_token,
            params={"format": "full"},
        )
        root = payload.get("payload") if isinstance(payload, dict) else None
        return _attachment_metadata(root)

    async def create_draft(self, access_token: str, message: EmailCompose) -> DraftResponse:
        payload = await self._request_json(
            "POST",
            "/users/me/drafts",
            access_token=access_token,
            json_body={"message": {"raw": _raw_message(message)}},
        )
        if not isinstance(payload, dict):
            raise ProviderRequestError("Gmail returned an invalid draft.")
        return DraftResponse(
            id=_required_string(payload, "id"),
            provider=EmailProvider.GMAIL,
            subject=message.subject,
            recipient_count=len(message.to + message.cc + message.bcc),
        )

    async def send_message(self, access_token: str, message: EmailCompose) -> None:
        await self._request_json(
            "POST",
            "/users/me/messages/send",
            access_token=access_token,
            json_body={"raw": _raw_message(message)},
        )

    async def list_events(self, access_token: str, *, limit: int) -> CalendarEventPage:
        payload = await self._request_json(
            "GET",
            "/calendars/primary/events",
            access_token=access_token,
            base_url=self._settings.google_calendar_api_url,
            params={
                "maxResults": limit,
                "singleEvents": "true",
                "orderBy": "startTime",
                "timeMin": datetime.now(UTC).isoformat(),
            },
        )
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ProviderRequestError("Google Calendar returned an invalid event collection.")
        events = [_google_calendar_event(item) for item in items[:limit]]
        return CalendarEventPage(data=events, returned=len(events))

    async def create_event(
        self,
        access_token: str,
        event: CalendarEventCreate,
    ) -> CalendarEvent:
        payload = await self._request_json(
            "POST",
            "/calendars/primary/events",
            access_token=access_token,
            base_url=self._settings.google_calendar_api_url,
            json_body=_google_event_payload(event),
        )
        if not isinstance(payload, dict):
            raise ProviderRequestError("Google Calendar returned an invalid event.")
        return _google_calendar_event(payload)

    async def update_event(
        self,
        access_token: str,
        event_id: str,
        event: CalendarEventUpdate,
    ) -> CalendarEvent:
        payload = await self._request_json(
            "PATCH",
            f"/calendars/primary/events/{quote(event_id, safe='')}",
            access_token=access_token,
            base_url=self._settings.google_calendar_api_url,
            json_body=_google_event_payload(event),
        )
        if not isinstance(payload, dict):
            raise ProviderRequestError("Google Calendar returned an invalid event.")
        return _google_calendar_event(payload)

    async def delete_event(self, access_token: str, event_id: str) -> None:
        await self._request(
            "DELETE",
            f"/calendars/primary/events/{quote(event_id, safe='')}",
            access_token=access_token,
            base_url=self._settings.google_calendar_api_url,
        )

    async def _token_request(self, form: dict[str, str]) -> Any:
        client_id, client_secret = self._oauth_credentials()
        return await self._request_json(
            "POST",
            "/token",
            form={**form, "client_id": client_id, "client_secret": client_secret},
            base_url=self._settings.gmail_token_url,
        )

    def _oauth_credentials(self) -> tuple[str, str]:
        client_id = self._settings.gmail_oauth_client_id
        client_secret = self._settings.gmail_oauth_client_secret
        if not client_id or client_secret is None:
            raise InvalidRequestError("Gmail OAuth is not configured for this connector service.")
        return client_id, client_secret.get_secret_value()


def _raw_message(message: EmailCompose) -> str:
    mime = EmailMessage()
    mime["To"] = ", ".join(message.to)
    if message.cc:
        mime["Cc"] = ", ".join(message.cc)
    if message.bcc:
        mime["Bcc"] = ", ".join(message.bcc)
    mime["Subject"] = message.subject
    mime.set_content(message.text_body or "This message contains HTML content.")
    if message.html_body:
        mime.add_alternative(message.html_body, subtype="html")
    return base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii").rstrip("=")


def _google_event_payload(event: CalendarEventCreate | CalendarEventUpdate) -> dict[str, Any]:
    include_all = isinstance(event, CalendarEventCreate)
    included = event.model_fields_set
    payload: dict[str, Any] = {}
    if include_all or "title" in included:
        payload["summary"] = event.title
    if include_all or "description" in included:
        payload["description"] = event.description or ""
    timezone = event.timezone or "UTC"
    if (include_all or "start" in included) and event.start is not None:
        payload["start"] = {"dateTime": event.start.isoformat(), "timeZone": timezone}
    if (include_all or "end" in included) and event.end is not None:
        payload["end"] = {"dateTime": event.end.isoformat(), "timeZone": timezone}
    if include_all or "location" in included:
        payload["location"] = event.location or ""
    if include_all or "attendees" in included:
        payload["attendees"] = [{"email": address} for address in (event.attendees or [])]
    return payload


def _google_calendar_event(payload: dict[str, Any]) -> CalendarEvent:
    start = payload.get("start") if isinstance(payload.get("start"), dict) else {}
    end = payload.get("end") if isinstance(payload.get("end"), dict) else {}
    attendee_values = payload.get("attendees")
    attendees: list[str] = []
    if isinstance(attendee_values, list):
        for attendee in attendee_values:
            address = attendee.get("email") if isinstance(attendee, dict) else None
            if isinstance(address, str):
                attendees.append(address.lower())
    return CalendarEvent(
        id=_required_string(payload, "id"),
        title=_optional_string(payload.get("summary")) or "(untitled)",
        start=_google_event_datetime(start),
        end=_google_event_datetime(end),
        timezone=_optional_string(start.get("timeZone")),
        description=_optional_string(payload.get("description")),
        location=_optional_string(payload.get("location")),
        attendees=attendees,
        web_url=_optional_string(payload.get("htmlLink")),
    )


def _google_event_datetime(value: dict[str, Any]) -> datetime | None:
    raw = value.get("dateTime") or value.get("date")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _summary(payload: Any) -> MessageSummary:
    if not isinstance(payload, dict):
        raise ProviderRequestError("Gmail returned an invalid message.")
    headers = _headers(payload)
    labels = payload.get("labelIds") if isinstance(payload.get("labelIds"), list) else []
    root = payload.get("payload")
    return MessageSummary(
        id=_required_string(payload, "id"),
        thread_id=_optional_string(payload.get("threadId")),
        subject=headers.get("subject") or "(no subject)",
        sender=(_addresses(headers.get("from")) or [None])[0],
        recipients=_addresses(headers.get("to")),
        received_at=_date(headers.get("date")),
        snippet=(_optional_string(payload.get("snippet")) or "")[:1000],
        has_attachments=bool(_attachment_metadata(root)),
        is_read="UNREAD" not in labels,
    )


def _detail(payload: dict[str, Any]) -> MessageDetail:
    summary = _summary(payload)
    headers = _headers(payload)
    content_type, content = _message_body(payload.get("payload"))
    return MessageDetail(
        **summary.model_dump(),
        cc_recipients=_addresses(headers.get("cc")),
        bcc_recipients=_addresses(headers.get("bcc")),
        body=MessageBody(content_type=content_type, content=content) if content else None,
    )


def _headers(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get("payload")
    values = payload.get("headers") if isinstance(payload, dict) else None
    if not isinstance(values, list):
        return {}
    headers: dict[str, str] = {}
    for item in values:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if isinstance(name, str) and isinstance(value, str):
            headers[name.lower()] = value
    return headers


def _addresses(value: str | None) -> list[EmailIdentity]:
    if not value:
        return []
    result: list[EmailIdentity] = []
    for name, address in getaddresses([value]):
        try:
            item = identity(address, name)
        except ValueError:
            continue
        if item:
            result.append(item)
    return result


def _message_body(root: Any) -> tuple[str, str]:
    if not isinstance(root, dict):
        return "text", ""
    parts = root.get("parts")
    if isinstance(parts, list):
        candidates: list[tuple[str, str]] = []
        for part in parts:
            content_type, content = _message_body(part)
            if content:
                candidates.append((content_type, content))
        for candidate in candidates:
            if candidate[0] == "text/plain":
                return candidate
        if candidates:
            return candidates[0]
    mime_type = _optional_string(root.get("mimeType")) or "text/plain"
    body = root.get("body")
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, str) or not data:
        return mime_type, ""
    try:
        decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
            "utf-8", errors="replace"
        )
    except (ValueError, TypeError):
        return mime_type, ""
    return mime_type, decoded[:250_000]


def _attachment_metadata(root: Any) -> list[AttachmentMetadata]:
    if not isinstance(root, dict):
        return []
    results: list[AttachmentMetadata] = []
    filename = root.get("filename")
    body = root.get("body")
    attachment_id = body.get("attachmentId") if isinstance(body, dict) else None
    if isinstance(filename, str) and filename and isinstance(attachment_id, str):
        results.append(
            AttachmentMetadata(
                id=attachment_id,
                name=filename,
                content_type=_optional_string(root.get("mimeType")),
                size=_optional_int(body.get("size")),
                inline=False,
            )
        )
    parts = root.get("parts")
    if isinstance(parts, list):
        for part in parts:
            results.extend(_attachment_metadata(part))
    return results


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ProviderRequestError("Gmail returned an invalid object.")
    return value


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

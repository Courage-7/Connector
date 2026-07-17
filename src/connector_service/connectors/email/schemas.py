"""Strict provider-neutral contracts for Outlook and Gmail mailboxes."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from connector_service.core.contracts import StrictModel

EMAIL_PATTERN = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
MAX_RECIPIENTS = 20


class EmailProvider(StrEnum):
    OUTLOOK = "outlook"
    GMAIL = "gmail"


class EmailOAuthStart(StrictModel):
    return_to: str | None = Field(default=None, pattern=r"^/app/?$")
    login_hint: str | None = Field(default=None, max_length=320)

    @field_validator("login_hint")
    @classmethod
    def validate_login_hint(cls, value: str | None) -> str | None:
        return validate_email_address(value) if value else None


class EmailOAuthStartResponse(StrictModel):
    authorization_url: str
    expires_at: datetime


class EmailConnectionResponse(StrictModel):
    id: str
    connector: str
    status: str
    external_ref: str | None
    name: str | None
    created_at: datetime


class EmailOAuthCallbackResponse(StrictModel):
    connection: EmailConnectionResponse
    next_step: str = "The mailbox is connected and ready for governed access."


class EmailIdentity(StrictModel):
    address: str
    display_name: str | None = Field(default=None, max_length=320)

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str) -> str:
        return validate_email_address(value)


class MailFolder(StrictModel):
    id: str = Field(min_length=1, max_length=2048)
    name: str = Field(min_length=1, max_length=500)
    unread_count: int | None = Field(default=None, ge=0)
    total_count: int | None = Field(default=None, ge=0)


class MessageSearch(StrictModel):
    query: str | None = Field(default=None, max_length=500)
    folder_id: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=25, ge=1, le=50)


class MessageSummary(StrictModel):
    id: str
    thread_id: str | None = None
    subject: str
    sender: EmailIdentity | None
    recipients: list[EmailIdentity] = Field(default_factory=list)
    received_at: datetime | None = None
    snippet: str = Field(default="", max_length=1000)
    has_attachments: bool = False
    is_read: bool | None = None


class MessageBody(StrictModel):
    content_type: str
    content: str = Field(max_length=250_000)


class MessageDetail(MessageSummary):
    cc_recipients: list[EmailIdentity] = Field(default_factory=list)
    bcc_recipients: list[EmailIdentity] = Field(default_factory=list)
    body: MessageBody | None = None


class AttachmentMetadata(StrictModel):
    id: str
    name: str
    content_type: str | None = None
    size: int | None = Field(default=None, ge=0)
    inline: bool = False


class MessagePage(StrictModel):
    data: list[MessageSummary]
    returned: int


class MessageThread(StrictModel):
    id: str
    messages: list[MessageDetail]


class EmailCompose(StrictModel):
    to: list[str] = Field(min_length=1, max_length=MAX_RECIPIENTS)
    cc: list[str] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    bcc: list[str] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    subject: str = Field(min_length=1, max_length=998)
    text_body: str | None = Field(default=None, max_length=100_000)
    html_body: str | None = Field(default=None, max_length=200_000)
    reply_to_message_id: str | None = Field(default=None, max_length=2048)

    @field_validator("to", "cc", "bcc")
    @classmethod
    def validate_recipients(cls, values: list[str]) -> list[str]:
        normalized = [validate_email_address(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("recipient lists must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def validate_message(self) -> EmailCompose:
        if not self.text_body and not self.html_body:
            raise ValueError("text_body or html_body is required")
        all_recipients = self.to + self.cc + self.bcc
        if len(all_recipients) > MAX_RECIPIENTS:
            raise ValueError(f"a message can have at most {MAX_RECIPIENTS} recipients")
        if len(all_recipients) != len(set(all_recipients)):
            raise ValueError("a recipient must appear only once")
        return self


class DraftResponse(StrictModel):
    id: str
    provider: EmailProvider
    subject: str
    recipient_count: int


class EmailSendRequestResponse(StrictModel):
    id: str
    connection_id: str
    provider: EmailProvider
    status: str
    message: EmailCompose
    requested_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    decision_note: str | None


class EmailSendStatusResponse(StrictModel):
    id: str
    connection_id: str
    provider: EmailProvider
    status: str
    requested_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    decision_note: str | None


class EmailDecision(StrictModel):
    note: str | None = Field(default=None, max_length=500)


class EmailSendExecutionResponse(StrictModel):
    request_id: str
    provider: EmailProvider
    status: str


class EmailAuditResponse(StrictModel):
    id: str
    connection_id: str
    send_request_id: str | None
    provider: EmailProvider
    action: str
    actor_type: str
    recipient_count: int
    attachment_count: int
    status: str
    returned_items: int | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None


def validate_email_address(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) > 320 or not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("must be a valid email address")
    return normalized

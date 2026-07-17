"""Add email send approvals and redacted email audits.

Revision ID: 7a3c8f12e9b4
Revises: 3d52dbf38a57
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a3c8f12e9b4"
down_revision: str | None = "3d52dbf38a57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_send_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("encrypted_message", sa.LargeBinary(), nullable=False),
        sa.Column("payload_digest", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["connection_id"], ["provider_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_email_send_requests_connection_id", "email_send_requests", ["connection_id"]
    )
    op.create_index("ix_email_send_requests_expires_at", "email_send_requests", ["expires_at"])
    op.create_index("ix_email_send_requests_project_id", "email_send_requests", ["project_id"])
    op.create_index("ix_email_send_requests_provider", "email_send_requests", ["provider"])
    op.create_index("ix_email_send_requests_status", "email_send_requests", ["status"])

    op.create_table(
        "email_audit_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("send_request_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("actor_type", sa.String(length=24), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column("attachment_count", sa.Integer(), nullable=False),
        sa.Column("payload_digest", sa.LargeBinary(), nullable=True),
        sa.Column("provider_reference", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("returned_items", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["connection_id"], ["provider_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["send_request_id"], ["email_send_requests.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_audit_records_action", "email_audit_records", ["action"])
    op.create_index(
        "ix_email_audit_records_connection_id", "email_audit_records", ["connection_id"]
    )
    op.create_index("ix_email_audit_records_created_at", "email_audit_records", ["created_at"])
    op.create_index("ix_email_audit_records_project_id", "email_audit_records", ["project_id"])
    op.create_index("ix_email_audit_records_provider", "email_audit_records", ["provider"])
    op.create_index("ix_email_audit_records_status", "email_audit_records", ["status"])


def downgrade() -> None:
    op.drop_table("email_audit_records")
    op.drop_table("email_send_requests")

"""Add dashboard sessions and query governance.

Revision ID: 3d52dbf38a57
Revises: 0002
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3d52dbf38a57"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dashboard_login_tickets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("token_digest", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dashboard_login_tickets_expires_at",
        "dashboard_login_tickets",
        ["expires_at"],
    )
    op.create_index(
        "ix_dashboard_login_tickets_project_id",
        "dashboard_login_tickets",
        ["project_id"],
    )
    op.create_index(
        "ix_dashboard_login_tickets_token_digest",
        "dashboard_login_tickets",
        ["token_digest"],
        unique=True,
    )

    op.create_table(
        "dashboard_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("token_digest", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dashboard_sessions_expires_at", "dashboard_sessions", ["expires_at"])
    op.create_index("ix_dashboard_sessions_project_id", "dashboard_sessions", ["project_id"])
    op.create_index(
        "ix_dashboard_sessions_token_digest",
        "dashboard_sessions",
        ["token_digest"],
        unique=True,
    )

    op.create_table(
        "agent_access_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("approval_mode", sa.String(length=24), nullable=False),
        sa.Column("max_rows", sa.Integer(), nullable=False),
        sa.Column("allowed_schemas", sa.JSON(), nullable=False),
        sa.Column("masked_columns", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["provider_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "connection_id",
            name="uq_agent_policy_project_connection",
        ),
    )
    op.create_index(
        "ix_agent_access_policies_connection_id",
        "agent_access_policies",
        ["connection_id"],
    )
    op.create_index("ix_agent_access_policies_project_id", "agent_access_policies", ["project_id"])

    op.create_table(
        "agent_query_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("query", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["connection_id"], ["provider_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_query_requests_connection_id", "agent_query_requests", ["connection_id"]
    )
    op.create_index("ix_agent_query_requests_project_id", "agent_query_requests", ["project_id"])
    op.create_index("ix_agent_query_requests_status", "agent_query_requests", ["status"])

    op.create_table(
        "query_audit_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("query_request_id", sa.String(length=36), nullable=True),
        sa.Column("actor_type", sa.String(length=24), nullable=False),
        sa.Column("schema_name", sa.String(length=63), nullable=False),
        sa.Column("table_name", sa.String(length=63), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("order_by", sa.JSON(), nullable=False),
        sa.Column("row_limit", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("returned_rows", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["connection_id"], ["provider_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["query_request_id"], ["agent_query_requests.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_query_audit_records_connection_id", "query_audit_records", ["connection_id"]
    )
    op.create_index("ix_query_audit_records_created_at", "query_audit_records", ["created_at"])
    op.create_index("ix_query_audit_records_project_id", "query_audit_records", ["project_id"])
    op.create_index("ix_query_audit_records_status", "query_audit_records", ["status"])


def downgrade() -> None:
    op.drop_table("query_audit_records")
    op.drop_table("agent_query_requests")
    op.drop_table("agent_access_policies")
    op.drop_table("dashboard_sessions")
    op.drop_table("dashboard_login_tickets")

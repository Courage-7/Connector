"""Add OAuth attempts and provider connections.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("connector", sa.String(length=40), nullable=False),
        sa.Column("state_digest", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_context", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oauth_attempts_connector", "oauth_attempts", ["connector"])
    op.create_index("ix_oauth_attempts_expires_at", "oauth_attempts", ["expires_at"])
    op.create_index("ix_oauth_attempts_project_id", "oauth_attempts", ["project_id"])
    op.create_index(
        "ix_oauth_attempts_state_digest",
        "oauth_attempts",
        ["state_digest"],
        unique=True,
    )

    op.create_table(
        "provider_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("connector", sa.String(length=40), nullable=False),
        sa.Column("external_ref", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("encrypted_secret", sa.LargeBinary(), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "connector",
            "external_ref",
            name="uq_connection_project_connector_external_ref",
        ),
    )
    op.create_index("ix_provider_connections_connector", "provider_connections", ["connector"])
    op.create_index("ix_provider_connections_project_id", "provider_connections", ["project_id"])


def downgrade() -> None:
    op.drop_table("provider_connections")
    op.drop_table("oauth_attempts")

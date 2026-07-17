"""Create connector service core tables.

Revision ID: 0001
Revises:
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("connector", sa.String(length=40), nullable=False),
        sa.Column("encrypted_secret", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credentials_connector", "credentials", ["connector"])

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "project_api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("prefix", sa.String(length=12), nullable=False),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("digest", sa.LargeBinary(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_api_keys_prefix",
        "project_api_keys",
        ["prefix"],
        unique=True,
    )
    op.create_index("ix_project_api_keys_project_id", "project_api_keys", ["project_id"])

    op.create_table(
        "connector_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("credential_id", sa.String(length=36), nullable=False),
        sa.Column("connector", sa.String(length=40), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["credential_id"], ["credentials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "credential_id", "connector", name="uq_grant_project_credential"
        ),
    )
    op.create_index("ix_connector_grants_connector", "connector_grants", ["connector"])
    op.create_index("ix_connector_grants_credential_id", "connector_grants", ["credential_id"])
    op.create_index("ix_connector_grants_project_id", "connector_grants", ["project_id"])


def downgrade() -> None:
    op.drop_table("connector_grants")
    op.drop_table("project_api_keys")
    op.drop_table("projects")
    op.drop_table("credentials")

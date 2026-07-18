"""Contracts for user-authorized Supabase connections and read-only queries."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from connector_service.core.contracts import StrictModel
from connector_service.providers.supabase.schemas import SortDirection


class SupabaseOAuthStart(StrictModel):
    organization_slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    return_to: str | None = Field(
        default=None,
        pattern=r"^/app/?$",
    )


class SupabaseOAuthStartResponse(StrictModel):
    authorization_url: str
    expires_at: datetime


class ProviderConnectionResponse(StrictModel):
    id: str
    connector: str
    status: str
    external_ref: str | None
    name: str | None
    created_at: datetime


class SupabaseOAuthCallbackResponse(StrictModel):
    connection: ProviderConnectionResponse
    next_step: str = "Select a Supabase project from this connection's projects endpoint."


class SupabaseProjectSummary(StrictModel):
    ref: str
    name: str = Field(min_length=1, max_length=120)
    organization_slug: str | None = Field(default=None, max_length=63)
    region: str | None = None
    status: str | None = None


class SupabaseProjectSelection(StrictModel):
    project_ref: str = Field(pattern=r"^[a-z0-9]{20}$")


class TableKind(StrEnum):
    TABLE = "table"
    VIEW = "view"


class TableSummary(StrictModel):
    schema_name: str
    table_name: str
    kind: TableKind

    @field_validator("schema_name", "table_name")
    @classmethod
    def validate_relation_identifier(cls, value: str) -> str:
        return validate_catalog_identifier(value)


class ColumnSummary(StrictModel):
    name: str
    data_type: str
    nullable: bool
    ordinal_position: int

    @field_validator("name")
    @classmethod
    def validate_column_name(cls, value: str) -> str:
        return validate_catalog_identifier(value)


class TableDescription(StrictModel):
    schema_name: str
    table_name: str
    columns: list[ColumnSummary]

    @field_validator("schema_name", "table_name")
    @classmethod
    def validate_relation_identifier(cls, value: str) -> str:
        return validate_catalog_identifier(value)


class EqualityFilter(StrictModel):
    column: str
    value: Any

    @field_validator("column")
    @classmethod
    def validate_column(cls, value: str) -> str:
        return validate_catalog_identifier(value)


class TableOrder(StrictModel):
    column: str
    direction: SortDirection = SortDirection.ASC

    @field_validator("column")
    @classmethod
    def validate_column(cls, value: str) -> str:
        return validate_catalog_identifier(value)


class TableQuery(StrictModel):
    schema_name: str = "public"
    table_name: str
    columns: list[str] = Field(min_length=1, max_length=50)
    filters: list[EqualityFilter] = Field(default_factory=list, max_length=20)
    order: list[TableOrder] = Field(default_factory=list, max_length=5)
    limit: int = Field(default=50, ge=1, le=100)

    @field_validator("schema_name", "table_name")
    @classmethod
    def validate_relation_identifier(cls, value: str) -> str:
        return validate_catalog_identifier(value)

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, values: list[str]) -> list[str]:
        normalized = [validate_catalog_identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("columns must not contain duplicates")
        return normalized


def validate_catalog_identifier(value: str) -> str:
    if not value or len(value.encode("utf-8")) > 63:
        raise ValueError("must be a valid PostgreSQL identifier")
    if "\x00" in value or not value.isprintable():
        raise ValueError("must be a valid PostgreSQL identifier")
    return value


class TableQueryResponse(StrictModel):
    data: list[dict[str, Any]]
    returned: int
    limit: int

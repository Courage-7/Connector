"""Strict Supabase credential, grant, and action schemas."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator

from connector_service.core.contracts import StrictModel

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(value: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError("must be a simple PostgreSQL identifier")
    return value


class SupabaseCredentialInput(StrictModel):
    project_url: AnyHttpUrl
    api_key: SecretStr = Field(min_length=20)
    authorization_token: SecretStr | None = Field(default=None, min_length=20)

    @field_validator("project_url")
    @classmethod
    def require_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        is_local_http = value.scheme == "http" and value.host in local_hosts
        if value.scheme != "https" and not is_local_http:
            raise ValueError("Supabase project URLs must use HTTPS except on localhost")
        return value

    def secret_document(self) -> dict[str, str]:
        document = {
            "project_url": str(self.project_url).rstrip("/"),
            "api_key": self.api_key.get_secret_value(),
        }
        if self.authorization_token is not None:
            document["authorization_token"] = self.authorization_token.get_secret_value()
        return document


class SupabaseAction(StrEnum):
    LIST_RESOURCES = "list_resources"
    DESCRIBE_RESOURCE = "describe_resource"
    LIST_ROWS = "list_rows"
    GET_ROW = "get_row"
    CALL_RPC = "call_rpc"


class ResourcePolicy(StrictModel):
    resource: str
    columns: list[str] = Field(min_length=1)
    filter_columns: list[str] = Field(default_factory=list)
    order_columns: list[str] = Field(default_factory=list)
    id_column: str | None = None
    max_page_size: int = Field(default=100, ge=1, le=1000)

    @field_validator("resource", "id_column")
    @classmethod
    def identifiers_or_none(cls, value: str | None) -> str | None:
        return validate_identifier(value) if value is not None else value

    @field_validator("columns", "filter_columns", "order_columns")
    @classmethod
    def identifier_lists(cls, values: list[str]) -> list[str]:
        normalized = [validate_identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def validate_subsets(self) -> ResourcePolicy:
        allowed = set(self.columns)
        if not set(self.filter_columns).issubset(allowed):
            raise ValueError("filter_columns must be included in columns")
        if not set(self.order_columns).issubset(allowed):
            raise ValueError("order_columns must be included in columns")
        if self.id_column is not None and self.id_column not in allowed:
            raise ValueError("id_column must be included in columns")
        return self


class RpcPolicy(StrictModel):
    name: str
    allowed_arguments: list[str] = Field(default_factory=list)
    max_rows: int = Field(default=100, ge=1, le=1000)

    @field_validator("name")
    @classmethod
    def rpc_identifier(cls, value: str) -> str:
        return validate_identifier(value)

    @field_validator("allowed_arguments")
    @classmethod
    def argument_identifiers(cls, values: list[str]) -> list[str]:
        normalized = [validate_identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("must not contain duplicates")
        return normalized


class SupabaseGrantPolicy(StrictModel):
    resources: list[ResourcePolicy] = Field(default_factory=list)
    rpcs: list[RpcPolicy] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_names(self) -> SupabaseGrantPolicy:
        resource_names = [policy.resource for policy in self.resources]
        rpc_names = [policy.name for policy in self.rpcs]
        if len(resource_names) != len(set(resource_names)):
            raise ValueError("resource policies must have unique names")
        if len(rpc_names) != len(set(rpc_names)):
            raise ValueError("RPC policies must have unique names")
        return self

    def resource(self, name: str) -> ResourcePolicy | None:
        return next((policy for policy in self.resources if policy.resource == name), None)

    def rpc(self, name: str) -> RpcPolicy | None:
        return next((policy for policy in self.rpcs if policy.name == name), None)


class FilterOperator(StrEnum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    LIKE = "like"
    ILIKE = "ilike"
    IS = "is"
    IN = "in"


class RowFilter(StrictModel):
    column: str
    operator: FilterOperator
    value: Any

    @field_validator("column")
    @classmethod
    def column_identifier(cls, value: str) -> str:
        return validate_identifier(value)

    @model_validator(mode="after")
    def validate_value_shape(self) -> RowFilter:
        if self.operator is FilterOperator.IN:
            if not isinstance(self.value, list) or not self.value or len(self.value) > 100:
                raise ValueError("in filters require a non-empty list of at most 100 values")
        elif isinstance(self.value, (dict, list)):
            raise ValueError("this filter operator requires a scalar value")
        if self.operator is FilterOperator.IS and self.value not in {None, True, False}:
            raise ValueError("is filters accept only null or boolean values")
        return self


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class RowOrder(StrictModel):
    column: str
    direction: SortDirection = SortDirection.ASC
    nulls: Literal["first", "last"] | None = None

    @field_validator("column")
    @classmethod
    def column_identifier(cls, value: str) -> str:
        return validate_identifier(value)


class ListResourcesInput(StrictModel):
    pass


class DescribeResourceInput(StrictModel):
    resource: str

    @field_validator("resource")
    @classmethod
    def resource_identifier(cls, value: str) -> str:
        return validate_identifier(value)


class ListRowsInput(StrictModel):
    resource: str
    columns: list[str] | None = None
    filters: list[RowFilter] = Field(default_factory=list, max_length=20)
    order: list[RowOrder] = Field(default_factory=list, max_length=5)
    limit: int = Field(default=50, ge=1, le=1000)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator("resource")
    @classmethod
    def resource_identifier(cls, value: str) -> str:
        return validate_identifier(value)

    @field_validator("columns")
    @classmethod
    def column_identifiers(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return values
        if not values:
            raise ValueError("columns cannot be empty")
        normalized = [validate_identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("columns must not contain duplicates")
        return normalized


class GetRowInput(StrictModel):
    resource: str
    identifier: str | int
    columns: list[str] | None = None

    @field_validator("resource")
    @classmethod
    def resource_identifier(cls, value: str) -> str:
        return validate_identifier(value)

    @field_validator("columns")
    @classmethod
    def column_identifiers(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return values
        if not values:
            raise ValueError("columns cannot be empty")
        normalized = [validate_identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("columns must not contain duplicates")
        return normalized


class CallRpcInput(StrictModel):
    rpc: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("rpc")
    @classmethod
    def rpc_identifier(cls, value: str) -> str:
        return validate_identifier(value)

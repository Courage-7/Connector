"""Policy enforcement and action dispatch for Supabase."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import ValidationError

from connector_service.config import Settings
from connector_service.connectors.supabase.client import SupabaseDataClient
from connector_service.connectors.supabase.schemas import (
    CallRpcInput,
    DescribeResourceInput,
    GetRowInput,
    ListResourcesInput,
    ListRowsInput,
    ResourcePolicy,
    SupabaseAction,
    SupabaseGrantPolicy,
)
from connector_service.core.contracts import (
    ActionExecutionResponse,
    ActionMeta,
    StrictModel,
)
from connector_service.core.exceptions import (
    AuthorizationError,
    InvalidRequestError,
    NotFoundError,
    ProviderRequestError,
)
from connector_service.core.pagination import CursorCodec, query_fingerprint
from connector_service.core.registry import ActionContext


class SupabaseConnector:
    name = "supabase"
    actions = frozenset(action.value for action in SupabaseAction)

    def __init__(
        self,
        settings: Settings,
        cursor_codec: CursorCodec,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._cursor_codec = cursor_codec
        self._transport = transport

    async def execute(
        self,
        action: str,
        *,
        context: ActionContext,
        credential: dict[str, Any],
        policy: dict[str, Any],
        payload: dict[str, Any],
    ) -> ActionExecutionResponse:
        del context
        grant_policy = self._validate(SupabaseGrantPolicy, policy)
        action_name = SupabaseAction(action)
        if action_name is SupabaseAction.LIST_RESOURCES:
            request = self._validate(ListResourcesInput, payload)
            del request
            return self._list_resources(grant_policy)
        if action_name is SupabaseAction.DESCRIBE_RESOURCE:
            request = self._validate(DescribeResourceInput, payload)
            return self._describe_resource(grant_policy, request)

        project_url = credential.get("project_url")
        api_key = credential.get("api_key")
        authorization_token = credential.get("authorization_token")
        if not isinstance(project_url, str) or not isinstance(api_key, str):
            raise InvalidRequestError("The stored Supabase credential is invalid.")
        if authorization_token is not None and not isinstance(authorization_token, str):
            raise InvalidRequestError("The stored Supabase authorization token is invalid.")

        async with SupabaseDataClient(
            project_url=project_url,
            api_key=api_key,
            authorization_token=authorization_token,
            timeout_seconds=self._settings.provider_timeout_seconds,
            max_retries=self._settings.provider_max_retries,
            retry_base_seconds=self._settings.provider_retry_base_seconds,
            max_response_bytes=self._settings.max_provider_response_bytes,
            transport=self._transport,
        ) as client:
            if action_name is SupabaseAction.LIST_ROWS:
                request = self._validate(ListRowsInput, payload)
                return await self._list_rows(client, grant_policy, request)
            if action_name is SupabaseAction.GET_ROW:
                request = self._validate(GetRowInput, payload)
                return await self._get_row(client, grant_policy, request)
            request = self._validate(CallRpcInput, payload)
            return await self._call_rpc(client, grant_policy, request)

    @staticmethod
    def _validate(model: type[StrictModel], value: dict[str, Any]) -> Any:
        try:
            return model.model_validate(value)
        except ValidationError as exc:
            raise InvalidRequestError(
                details={"fields": [".".join(map(str, error["loc"])) for error in exc.errors()]}
            ) from exc

    @staticmethod
    def _list_resources(policy: SupabaseGrantPolicy) -> ActionExecutionResponse:
        data = [resource.resource for resource in policy.resources]
        return ActionExecutionResponse(
            data=data,
            meta=ActionMeta(
                connector="supabase", action=SupabaseAction.LIST_RESOURCES, returned=len(data)
            ),
        )

    @classmethod
    def _describe_resource(
        cls, policy: SupabaseGrantPolicy, request: DescribeResourceInput
    ) -> ActionExecutionResponse:
        resource = cls._resource(policy, request.resource)
        return ActionExecutionResponse(
            data=resource.model_dump(mode="json"),
            meta=ActionMeta(
                connector="supabase", action=SupabaseAction.DESCRIBE_RESOURCE, returned=1
            ),
        )

    async def _list_rows(
        self,
        client: SupabaseDataClient,
        policy: SupabaseGrantPolicy,
        request: ListRowsInput,
    ) -> ActionExecutionResponse:
        resource = self._resource(policy, request.resource)
        columns = self._columns(resource, request.columns)
        self._authorize_query(resource, request)
        limit = min(request.limit, resource.max_page_size, self._settings.max_page_size)
        fingerprint = query_fingerprint(
            {
                "resource": request.resource,
                "columns": columns,
                "filters": [item.model_dump(mode="json") for item in request.filters],
                "order": [item.model_dump(mode="json") for item in request.order],
                "limit": limit,
            }
        )
        offset = 0
        if request.cursor:
            offset = self._cursor_codec.decode(
                request.cursor, expected_fingerprint=fingerprint
            ).offset
        rows = await client.list_rows(
            resource=resource.resource,
            columns=columns,
            filters=request.filters,
            order=request.order,
            limit=limit,
            offset=offset,
        )
        if len(rows) > limit:
            raise ProviderRequestError("The provider returned more rows than requested.")
        next_cursor = None
        if len(rows) == limit:
            next_cursor = self._cursor_codec.encode(offset=offset + limit, fingerprint=fingerprint)
        return ActionExecutionResponse(
            data=rows,
            meta=ActionMeta(
                connector="supabase",
                action=SupabaseAction.LIST_ROWS,
                returned=len(rows),
                next_cursor=next_cursor,
            ),
        )

    async def _get_row(
        self,
        client: SupabaseDataClient,
        policy: SupabaseGrantPolicy,
        request: GetRowInput,
    ) -> ActionExecutionResponse:
        resource = self._resource(policy, request.resource)
        if resource.id_column is None:
            raise AuthorizationError("Row lookup is not enabled for this resource.")
        columns = self._columns(resource, request.columns)
        from connector_service.connectors.supabase.schemas import FilterOperator, RowFilter

        rows = await client.list_rows(
            resource=resource.resource,
            columns=columns,
            filters=[
                RowFilter(
                    column=resource.id_column,
                    operator=FilterOperator.EQ,
                    value=request.identifier,
                )
            ],
            order=[],
            limit=2,
            offset=0,
        )
        if not rows:
            raise NotFoundError("The requested row was not found.")
        if len(rows) > 1:
            raise InvalidRequestError("The configured identifier column is not unique.")
        return ActionExecutionResponse(
            data=rows[0],
            meta=ActionMeta(connector="supabase", action=SupabaseAction.GET_ROW, returned=1),
        )

    async def _call_rpc(
        self,
        client: SupabaseDataClient,
        policy: SupabaseGrantPolicy,
        request: CallRpcInput,
    ) -> ActionExecutionResponse:
        rpc_policy = policy.rpc(request.rpc)
        if rpc_policy is None:
            raise AuthorizationError("This RPC is not approved for the project.")
        unexpected = set(request.arguments) - set(rpc_policy.allowed_arguments)
        if unexpected:
            raise AuthorizationError(
                "One or more RPC arguments are not approved.",
                details={"arguments": sorted(unexpected)},
            )
        data = await client.call_rpc(
            rpc=rpc_policy.name,
            arguments=request.arguments,
            limit=rpc_policy.max_rows + 1,
        )
        if isinstance(data, list) and len(data) > rpc_policy.max_rows:
            raise InvalidRequestError("The RPC response exceeded its configured row limit.")
        returned = len(data) if isinstance(data, list) else 1
        return ActionExecutionResponse(
            data=data,
            meta=ActionMeta(
                connector="supabase", action=SupabaseAction.CALL_RPC, returned=returned
            ),
        )

    @staticmethod
    def _resource(policy: SupabaseGrantPolicy, name: str) -> ResourcePolicy:
        resource = policy.resource(name)
        if resource is None:
            raise AuthorizationError("This resource is not approved for the project.")
        return resource

    @staticmethod
    def _columns(resource: ResourcePolicy, requested: list[str] | None) -> list[str]:
        if requested is None:
            return resource.columns
        unexpected = set(requested) - set(resource.columns)
        if unexpected:
            raise AuthorizationError(
                "One or more columns are not approved.",
                details={"columns": sorted(unexpected)},
            )
        return requested

    @staticmethod
    def _authorize_query(resource: ResourcePolicy, request: ListRowsInput) -> None:
        filter_columns = {item.column for item in request.filters}
        order_columns = {item.column for item in request.order}
        denied_filters = filter_columns - set(resource.filter_columns)
        denied_orders = order_columns - set(resource.order_columns)
        if denied_filters:
            raise AuthorizationError(
                "One or more filter columns are not approved.",
                details={"columns": sorted(denied_filters)},
            )
        if denied_orders:
            raise AuthorizationError(
                "One or more ordering columns are not approved.",
                details={"columns": sorted(denied_orders)},
            )

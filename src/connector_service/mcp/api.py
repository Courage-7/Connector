"""Swagger-visible MCP discovery endpoint."""

from fastapi import APIRouter

from connector_service.core.contracts import StrictModel
from connector_service.mcp.server import MCP_TOOL_NAMES

router = APIRouter(prefix="/v1/mcp", tags=["MCP"])


class MCPInfo(StrictModel):
    endpoint: str
    transport: str
    authentication: str
    tools: list[str]


@router.get("", response_model=MCPInfo)
async def get_mcp_info() -> MCPInfo:
    return MCPInfo(
        endpoint="/mcp",
        transport="Streamable HTTP",
        authentication="Authorization: Bearer <token>",
        tools=list(MCP_TOOL_NAMES),
    )

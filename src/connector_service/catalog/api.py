"""Public provider and tool discovery endpoints."""

from fastapi import APIRouter, Request

from connector_service.catalog.models import ProviderManifest, ToolManifest
from connector_service.catalog.service import ProviderCatalogService

router = APIRouter(prefix="/v1/providers", tags=["Providers"])


@router.get("", response_model=list[ProviderManifest])
async def list_providers(request: Request) -> list[ProviderManifest]:
    catalog: ProviderCatalogService = request.app.state.catalog
    return catalog.list_providers()


@router.get("/{provider}", response_model=ProviderManifest)
async def get_provider(provider: str, request: Request) -> ProviderManifest:
    catalog: ProviderCatalogService = request.app.state.catalog
    return catalog.get_provider(provider)


@router.get("/{provider}/tools", response_model=list[ToolManifest])
async def list_provider_tools(provider: str, request: Request) -> list[ToolManifest]:
    catalog: ProviderCatalogService = request.app.state.catalog
    return catalog.get_provider(provider).tools

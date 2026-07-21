"""FastAPI application composition root."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.responses import Response

from connector_service import __version__
from connector_service.bootstrap.config import Settings, get_settings
from connector_service.catalog import api as catalog_api
from connector_service.catalog.service import ProviderCatalogService
from connector_service.connections import api as connections_api
from connector_service.connections.service import ConnectionService
from connector_service.core.exceptions import ServiceError
from connector_service.identity import api as identity_api
from connector_service.identity.authenticators import (
    Authenticator,
    StaticBearerAuthenticator,
    SupabaseJwtAuthenticator,
)
from connector_service.infrastructure.crypto import SecretCipher
from connector_service.infrastructure.database.session import Database
from connector_service.mcp import api as mcp_api
from connector_service.mcp.server import create_mcp_application
from connector_service.observability import configure_logging, request_id_context
from connector_service.providers.supabase import api as supabase_api
from connector_service.providers.supabase.config import SupabaseProviderConfig
from connector_service.providers.supabase.management import SupabaseManagementClient
from connector_service.providers.supabase.tools import SupabaseToolService

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    supabase_transport: httpx.AsyncBaseTransport | None = None,
    auth_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    runtime = settings or get_settings()
    configure_logging(runtime.log_level)
    database = Database(runtime.async_database_url)
    cipher = SecretCipher(runtime.token_encryption_key.get_secret_value())
    authenticator = _build_authenticator(runtime, transport=auth_transport)
    management = SupabaseManagementClient(
        SupabaseProviderConfig(
            client_id=runtime.supabase_oauth_client_id,
            client_secret=(
                runtime.supabase_oauth_client_secret.get_secret_value()
                if runtime.supabase_oauth_client_secret is not None
                else None
            ),
            redirect_uri=runtime.supabase_oauth_redirect_uri,
            management_api_url=runtime.supabase_management_api_url,
            timeout_seconds=runtime.provider_timeout_seconds,
            max_response_bytes=runtime.max_provider_response_bytes,
        ),
        transport=supabase_transport,
    )
    connection_service = ConnectionService(
        settings=runtime,
        cipher=cipher,
        supabase_client=management,
    )
    supabase_tools = SupabaseToolService(
        connections=connection_service,
        management=management,
    )
    raw_mcp_app, protected_mcp_app = create_mcp_application(
        database=database,
        authenticator=authenticator,
        tools=supabase_tools,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if runtime.auto_create_schema:
            await database.create_schema()
        async with raw_mcp_app.router.lifespan_context(raw_mcp_app):
            yield
        await database.dispose()

    app = FastAPI(
        title=runtime.app_name,
        version=__version__,
        description=(
            "B2C provider connections and typed tools over REST and authenticated MCP. "
            "Use the BearerAuth scheme for connections and tool execution."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        swagger_ui_parameters={
            "persistAuthorization": True,
            "displayRequestDuration": True,
        },
        lifespan=lifespan,
    )
    app.state.database = database
    app.state.authenticator = authenticator
    app.state.catalog = ProviderCatalogService(runtime)
    app.state.connection_service = connection_service
    app.state.supabase_tools = supabase_tools

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied = request.headers.get("X-Request-ID")
        request_id = (
            supplied if supplied and REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        )
        token = request_id_context.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_context.reset(token)

    @app.exception_handler(ServiceError)
    async def service_error_handler(
        _request: Request,
        exc: ServiceError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.safe_message,
                    "details": exc.details,
                    "request_id": request_id_context.get(),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        fields = [".".join(map(str, error["loc"])) for error in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "The request is invalid.",
                    "details": {"fields": fields},
                    "request_id": request_id_context.get(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        _request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error(
            "Unhandled application error",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "The service could not complete the request.",
                    "details": {},
                    "request_id": request_id_context.get(),
                }
            },
        )

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/docs", status_code=307)

    @app.get("/health", tags=["Operations"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": runtime.app_name, "version": __version__}

    app.include_router(identity_api.router)
    app.include_router(catalog_api.router)
    app.include_router(connections_api.router)
    app.include_router(supabase_api.router)
    app.include_router(mcp_api.router)
    app.mount("/", protected_mcp_app)
    return app


def _build_authenticator(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None,
) -> Authenticator:
    if settings.auth_mode == "static":
        if settings.service_bearer_token is None:
            raise ValueError("SERVICE_BEARER_TOKEN is required")
        return StaticBearerAuthenticator(
            token=settings.service_bearer_token.get_secret_value(),
            subject=settings.development_subject,
        )
    if not settings.supabase_auth_url:
        raise ValueError("SUPABASE_AUTH_URL is required")
    return SupabaseJwtAuthenticator(
        auth_url=settings.supabase_auth_url,
        audience=settings.supabase_auth_audience,
        cache_seconds=settings.jwks_cache_seconds,
        transport=transport,
    )

"""FastAPI application factory."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from connector_service.api import (
    actions,
    admin,
    agent,
    connections,
    dashboard,
    email_agent,
    email_connections,
    health,
)
from connector_service.api import (
    providers as provider_routes,
)
from connector_service.config import Settings, get_settings
from connector_service.core.exceptions import ServiceError
from connector_service.core.pagination import CursorCodec
from connector_service.core.registry import ConnectorRegistry
from connector_service.core.security import CredentialCipher
from connector_service.db.session import Database
from connector_service.observability import configure_logging, request_id_context
from connector_service.providers import (
    ProviderCapability,
    build_provider_catalog,
)

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    supabase_management_transport: httpx.AsyncBaseTransport | None = None,
    outlook_transport: httpx.AsyncBaseTransport | None = None,
    gmail_transport: httpx.AsyncBaseTransport | None = None,
    provider_transports: Mapping[str, httpx.AsyncBaseTransport] | None = None,
) -> FastAPI:
    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level)
    database = Database(runtime_settings.database_url)
    credential_cipher = CredentialCipher(
        runtime_settings.credential_encryption_key.get_secret_value()
    )
    cursor_codec = CursorCodec(runtime_settings.cursor_signing_key.get_secret_value())
    transports = dict(provider_transports or {})
    for name, transport in {
        "supabase": supabase_management_transport,
        "outlook": outlook_transport,
        "gmail": gmail_transport,
    }.items():
        if transport is not None:
            transports[name] = transport
    providers = build_provider_catalog(
        runtime_settings,
        cursor_codec,
        transports=transports,
    )
    registry = ConnectorRegistry()
    for connector in providers.connectors():
        registry.register(connector)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if runtime_settings.auto_create_schema:
            database.create_schema()
        yield
        database.dispose()

    app = FastAPI(
        title=runtime_settings.app_name,
        version="0.1.0",
        description="Policy-enforced access to reusable provider connectors.",
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.database = database
    app.state.credential_cipher = credential_cipher
    app.state.cursor_codec = cursor_codec
    app.state.registry = registry
    app.state.providers = providers

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
    async def service_error_handler(_request: Request, exc: ServiceError) -> JSONResponse:
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
        _request: Request, exc: RequestValidationError
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
    async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
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

    app.include_router(health.router)
    app.include_router(admin.router)
    app.include_router(dashboard.router)
    app.include_router(provider_routes.router)
    if providers.has_capability(ProviderCapability.DATABASE):
        app.include_router(connections.router)
        app.include_router(agent.agent_router)
        app.include_router(agent.dashboard_router)
    if providers.has_capability(ProviderCapability.EMAIL):
        app.include_router(email_connections.router)
        app.include_router(email_agent.agent_router)
        app.include_router(email_agent.dashboard_router)
    if providers.has_capability(ProviderCapability.ACTIONS):
        app.include_router(actions.router)
    web_dist = Path(__file__).with_name("web_dist")
    if web_dist.is_dir():

        @app.get("/", include_in_schema=False)
        async def landing_page() -> FileResponse:
            return FileResponse(web_dist / "index.html")

        app.mount("/app", StaticFiles(directory=web_dist, html=True), name="dashboard_app")
    return app

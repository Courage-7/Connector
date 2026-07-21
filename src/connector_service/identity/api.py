"""Bearer-authenticated identity endpoint and dependency."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from connector_service.core.contracts import StrictModel
from connector_service.core.exceptions import AuthenticationError
from connector_service.identity.authenticators import Authenticator
from connector_service.identity.principal import Principal

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Service Bearer token in development or Supabase Auth access token in production.",
)
router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


async def require_principal(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()
    authenticator: Authenticator = request.app.state.authenticator
    return await authenticator.authenticate(credentials.credentials)


class PrincipalResponse(StrictModel):
    subject: str
    tenant_id: str
    authentication_method: str


@router.get("/me", response_model=PrincipalResponse)
async def get_current_principal(
    principal: Annotated[Principal, Depends(require_principal)],
) -> PrincipalResponse:
    return PrincipalResponse(
        subject=principal.subject,
        tenant_id=principal.tenant_id,
        authentication_method=principal.authentication_method,
    )

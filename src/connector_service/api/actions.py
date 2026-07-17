"""Project-authenticated connector execution route."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from connector_service.api.dependencies import get_session, require_project
from connector_service.core.contracts import ActionExecutionRequest, ActionExecutionResponse
from connector_service.core.exceptions import AuthorizationError, InvalidRequestError
from connector_service.core.registry import ActionContext, ConnectorRegistry
from connector_service.core.security import CredentialCipher
from connector_service.db.models import Project
from connector_service.db.repositories import get_credential, get_grant_for_project

router = APIRouter(prefix="/v1/actions", tags=["connector actions"])


@router.post("/{connector}/{action}", response_model=ActionExecutionResponse)
async def execute_action(
    connector: str,
    action: str,
    body: ActionExecutionRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> ActionExecutionResponse:
    grant = get_grant_for_project(session, body.grant_id, project.id)
    if grant.connector != connector or action not in grant.actions:
        raise AuthorizationError()
    credential = get_credential(session, grant.credential_id)
    if credential.connector != connector:
        raise InvalidRequestError("The connector grant is internally inconsistent.")
    cipher: CredentialCipher = request.app.state.credential_cipher
    secret = cipher.decrypt(credential.encrypted_secret)
    registry: ConnectorRegistry = request.app.state.registry
    implementation = registry.get(connector)
    return await implementation.execute(
        action,
        context=ActionContext(project_id=project.id, grant_id=grant.id),
        credential=secret,
        policy=grant.policy,
        payload=body.input,
    )

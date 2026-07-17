"""Administrative provisioning routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from connector_service.api.dependencies import get_session, require_admin
from connector_service.api.schemas import (
    CredentialCreate,
    CredentialResponse,
    GrantCreate,
    GrantResponse,
    ProjectCreate,
    ProjectCreatedResponse,
)
from connector_service.core.exceptions import ConflictError, InvalidRequestError
from connector_service.core.registry import ConnectorRegistry
from connector_service.core.security import ApiKeyManager, CredentialCipher
from connector_service.db.models import ConnectorGrant, Credential, Project, ProjectApiKey
from connector_service.db.repositories import get_credential, get_project

router = APIRouter(
    prefix="/v1/admin",
    tags=["administration"],
    dependencies=[Depends(require_admin)],
)


@router.post("/credentials", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
def create_credential(
    body: CredentialCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> CredentialResponse:
    cipher: CredentialCipher = request.app.state.credential_cipher
    credential = Credential(
        name=body.name.strip(),
        connector=body.connector,
        encrypted_secret=cipher.encrypt(body.secret.secret_document()),
    )
    session.add(credential)
    session.commit()
    return CredentialResponse(
        id=credential.id,
        name=credential.name,
        connector=credential.connector,
    )


@router.post(
    "/projects",
    response_model=ProjectCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    body: ProjectCreate,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectCreatedResponse:
    material = ApiKeyManager.create()
    project = Project(name=body.name.strip())
    session.add(project)
    try:
        session.flush()
        session.add(
            ProjectApiKey(
                project_id=project.id,
                prefix=material.prefix,
                salt=material.salt,
                digest=material.digest,
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("A project with this name already exists.") from exc
    return ProjectCreatedResponse(id=project.id, name=project.name, api_key=material.plaintext)


@router.post("/grants", response_model=GrantResponse, status_code=status.HTTP_201_CREATED)
def create_grant(
    body: GrantCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> GrantResponse:
    project = get_project(session, body.project_id)
    credential = get_credential(session, body.credential_id)
    if not project.active:
        raise InvalidRequestError("The project is inactive.")
    if credential.connector != body.connector:
        raise InvalidRequestError("The credential does not belong to this connector.")
    registry: ConnectorRegistry = request.app.state.registry
    actions = [action.value for action in body.actions]
    unsupported = [action for action in actions if not registry.supports(body.connector, action)]
    if unsupported:
        raise InvalidRequestError(
            "One or more actions are not registered.", details={"actions": unsupported}
        )
    grant = ConnectorGrant(
        project_id=project.id,
        credential_id=credential.id,
        connector=body.connector,
        actions=sorted(set(actions)),
        policy=body.policy.model_dump(mode="json"),
        description=body.description,
    )
    session.add(grant)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("A grant already exists for this project and credential.") from exc
    return GrantResponse(
        id=grant.id,
        project_id=grant.project_id,
        credential_id=grant.credential_id,
        connector=grant.connector,
        actions=grant.actions,
    )

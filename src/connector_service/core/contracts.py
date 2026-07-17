"""Provider-neutral action contracts."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionExecutionRequest(StrictModel):
    grant_id: str = Field(min_length=1, max_length=64)
    input: dict[str, Any] = Field(default_factory=dict)


class ActionMeta(StrictModel):
    connector: str
    action: str
    returned: int | None = None
    next_cursor: str | None = None


class ActionExecutionResponse(StrictModel):
    data: Any
    meta: ActionMeta

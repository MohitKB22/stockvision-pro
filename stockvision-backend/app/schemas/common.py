"""
Shared response envelopes.

Design decision: successful responses return their payload directly (typed, no
wrapper) — wrapping every 200 in `{"data": ...}` buys nothing for a typed client
and doubles the nesting in every frontend selector. Errors, by contrast, ARE
uniformly enveloped, because that is where clients genuinely need one
predictable shape to branch on.
"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code — branch on this, not on `message`.")
    message: str = Field(description="Human-readable description, safe to display.")
    status: int
    context: dict[str, Any] | None = None
    request_id: str | None = Field(default=None, description="Correlates with the X-Request-ID response header.")


class ErrorEnvelope(BaseModel):
    """The body of every non-2xx response the API produces."""
    error: ErrorBody


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    skip: int
    limit: int
    has_more: bool


class OperationResult(BaseModel):
    success: bool = True
    message: str = ""
    id: str | None = None


class HealthResponse(BaseModel):
    status: str
    environment: str
    version: str
    database: str

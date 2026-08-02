"""Provider-neutral domain contracts owned by Chapter 1."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RetryClass(str, Enum):
    NONE = "none"
    CALLER = "caller"
    UPSTREAM = "upstream"
    CONFIG = "config"


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    MODEL_BAD_OUTPUT = "MODEL_BAD_OUTPUT"
    MODEL_CAPACITY = "MODEL_CAPACITY"
    CONFIG_INVALID = "CONFIG_INVALID"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class Budget(StrictModel):
    max_input_tokens: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)


class AuthorizationContext(StrictModel):
    scopes: list[str]
    decision_id: str


class RunContext(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: str
    trace_id: str
    tenant_id: str
    actor_id: str
    roles: list[str]
    purpose: str
    configuration_id: str
    configuration_versions: dict[str, str]
    deadline_at: datetime
    budget: Budget
    data_classification: Literal["public", "internal", "confidential"] = "internal"
    authorization_context: AuthorizationContext
    approval_reference: str | None = None
    idempotency_key: str | None = None


class ModelRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    question: str = Field(min_length=1)
    policy_version: str | None = None
    locale: str = "en-US"


class Citation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source_id: str
    title: str
    locator: str
    excerpt: str = Field(min_length=1)


class Usage(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    adapter: str


class Answer(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    answer_type: Literal["direct", "abstain"] = "direct"
    text: str
    citations: list[Citation] = Field(default_factory=list)
    abstention_reason: str | None = None

    @model_validator(mode="after")
    def _semantic_consistency(self) -> Answer:
        if self.answer_type == "abstain":
            if not self.abstention_reason:
                raise ValueError("abstain answers require abstention_reason")
        elif self.abstention_reason:
            raise ValueError("direct answers must not set abstention_reason")
        return self


class ModelFailure(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    code: ErrorCode
    retry_class: RetryClass
    message: str
    correlation_token: str | None = None


class ModelSuccess(StrictModel):
    kind: Literal["success"] = "success"
    answer: Answer
    usage: Usage


class ModelFailureResult(StrictModel):
    kind: Literal["failure"] = "failure"
    failure: ModelFailure


ModelResult = Annotated[ModelSuccess | ModelFailureResult, Field(discriminator="kind")]


class AnswerResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    answer: Answer
    usage: Usage
    trace_id: str
    configuration_id: str
    request_id: str


class ProblemDetail(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    code: ErrorCode
    message: str
    retry_class: RetryClass
    trace_id: str | None = None
    request_id: str | None = None
    details: dict[str, Any] | None = None


class DomainError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retry_class: RetryClass = RetryClass.NONE,
        http_status: int = 400,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_class = retry_class
        self.http_status = http_status
        self.trace_id = trace_id
        self.request_id = request_id

    def to_problem(self) -> ProblemDetail:
        return ProblemDetail(
            code=self.code,
            message=self.message,
            retry_class=self.retry_class,
            trace_id=self.trace_id,
            request_id=self.request_id,
        )

from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import HTTPException, RequestValidationError
from pydantic import AnyUrl, BaseModel, Field, field_validator


class Problem(BaseModel):
    """
    A description of an error that occurred while processing a request.

    See: https://datatracker.ietf.org/doc/html/rfc9457
    """

    type: AnyUrl | str = Field(default="about:blank")
    """A URI reference that identifies the problem type."""

    title: str | None = None
    """A short, human-readable summary of the problem type."""

    status: int | None = Field(ge=100, le=599, default=None)
    """The HTTP status code generated by the origin server for this occurrence of the problem."""

    detail: str | None = None
    """A human-readable explanation specific to this occurrence of the problem."""

    instance: AnyUrl | str | None = None
    """A URI reference that identifies the specific occurrence of the problem.
    Can be an absolute URI or a relative URI.
    """

    model_config = {"extra": "allow", "populate_by_name": True}

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, value: Any) -> AnyUrl | str:
        if value is None:
            return "about:blank"
        if isinstance(value, AnyUrl | str):
            return value
        return str(value)

    @field_validator("instance", mode="before")
    @classmethod
    def validate_instance(cls, value: Any) -> AnyUrl | str | None:
        if value is None:
            return None
        if isinstance(value, AnyUrl):
            return value
        if isinstance(value, str):
            if value.startswith("/"):
                return value
        return AnyUrl(value)

    @classmethod
    def validate(cls, value: dict[str, Any]) -> "Problem":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise ValueError(f"Expected a dictionary, got {type(value)}")
        return cls.model_validate(value)


class ProblemResponse(Response):
    media_type: str = "application/problem+json"

    def render(self, content: Any) -> bytes:
        problem: Problem

        if isinstance(content, Problem):
            problem = content
        elif isinstance(content, dict):
            problem = Problem.model_validate(content)
        else:
            problem = Problem(
                status=500,
                title="Application Error",
                detail=str(content),
            )

        self.status_code = problem.status or 500  # pylint: disable=attribute-defined-outside-init

        return problem.model_dump_json(
            exclude_none=True,
            exclude={"type"} if problem.type == "about:blank" else {},
        ).encode("utf-8")


async def problem_exception_handler(
    _request: Request, exc: Exception
) -> ProblemResponse:
    if isinstance(exc, HTTPException):
        content = Problem(
            status=exc.status_code,
            detail=exc.detail,
        )
    elif isinstance(exc, RequestValidationError):
        content = Problem(
            status=400,
            title="Bad Request",
            detail=str(exc),
            errors=exc.errors(),  # type: ignore
        )
    else:
        content = Problem(
            status=500,
            title="Application Error",
            detail=str(exc),
        )

    return ProblemResponse(content=content)

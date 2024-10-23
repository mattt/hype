from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError


class RequestPreferences(BaseModel):
    """
    The preferences for a request, as parsed from the `Prefer` header.

    See: https://www.rfc-editor.org/rfc/rfc7240.html
    """

    respond_async: bool | None = Field(alias="respond-async", default=None)
    """
    The "respond-async" preference indicates that the client prefers the
    server to respond asynchronously to a response.
    """

    return_: Literal["representation", "minimal"] | None = Field(
        alias="return", default=None
    )
    """
    The "return=representation" preference indicates that the client prefers
    that the server include an entity representing the current state of the
    resource in the response to a successful request.

    The "return=minimal" preference indicates that the client wishes the server
    to return only a minimal response to a successful request.
    """

    wait: int | None = Field(gt=0, default=None)
    """
    The "wait" preference can be used to establish an upper bound on the
    length of time, in seconds, the client expects it will take the server
    to process the request once it has been received.
    """

    handling: Literal["strict", "lenient"] | None = Field(default=None)
    """
    The "handling=strict" and "handling=lenient" preferences indicate how
    the client wishes the server to handle potential error conditions that
    can arise in the processing of a request.
    """

    model_config = {"extra": "forbid", "populate_by_name": True}

    @field_validator("wait", mode="before")
    @classmethod
    def validate_wait(cls, v: int | str) -> int:
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                raise PydanticCustomError(  # pylint: disable=raise-missing-from
                    "invalid_wait", "Invalid value for wait: {v}", {"v": v}
                ) from None
        return v

    def update(self, other: "RequestPreferences") -> None:
        """
        Update the preferences with the values from another preferences object.
        """
        for key, value in dict(other).items():
            if value is not None:
                setattr(self, key, value)

    @classmethod
    def parse(cls, value: str | None) -> "RequestPreferences":
        if not value:
            return cls()

        preferences = {}
        for token in value.lower().split(","):
            parts = [part.strip() for part in token.split("=", 1)]
            key, val = (parts[0], parts[1]) if len(parts) == 2 else (parts[0], True)

            if key == "respond-async":
                preferences[key] = True
            else:
                preferences[key] = val

        return cls.model_validate(preferences)


def parse_prefer_headers(value: list[str] | None) -> RequestPreferences:
    """
    Parse a list of `Prefer` headers into a single `RequestPreferences` object.

    If multiple `Prefer` headers are present, their preferences are combined
    into a single `RequestPreferences` object. In case of conflicting
    preferences, the last occurrence takes precedence. For example, if
    multiple headers specify different 'wait' times, the value from the
    last header in the list will be used.

    Non-conflicting preferences from different headers are merged. For instance,
    if one header specifies 'respond-async' and another specifies 'wait=100',
    both preferences will be included in the final `RequestPreferences` object.
    """

    preferences = RequestPreferences()
    for header in value or []:
        preferences.update(RequestPreferences.parse(header))
    return preferences

import re
from typing import Any

from pydantic import BaseModel, Field


class MediaRange(BaseModel):
    """
    Represents an HTTP Accept header media range with type, subtype, and quality value.

    This class handles parsing and matching of media types like "text/html" or "application/*",
    along with their parameters and quality values (q-values).

    For more details, see [RFC 7231, section 5.3.2](https://www.rfc-editor.org/rfc/rfc7231.html#section-5.3.2)
    """

    type: str = Field(
        description="The primary type", examples=["text", "application", "*"]
    )
    """The primary type (e.g., "text", "application", "*")"""

    subtype: str = Field(description="The subtype", examples=["html", "json", "*"])
    """The subtype (e.g., "html", "json", "*")"""

    parameters: dict[str, str] = Field(
        default_factory=dict,
        description="Optional media type parameters excluding q-value",
        examples=[{"charset": "utf-8"}],
    )
    """Optional media type parameters excluding q-value"""

    q: float = Field(
        ge=0,
        le=1,
        default=1.0,
        description="Quality value between 0 and 1",
        examples=[0.5, 1.0],
    )
    """Quality value between 0 and 1, defaults to 1.0."""

    @classmethod
    def validate(cls, value: Any) -> "MediaRange":
        """Validates and converts a string or MediaRange object into a MediaRange instance.

        Args:
            value: String (e.g., "text/html;q=0.9") or MediaRange object to validate

        Returns:
            MediaRange: A validated MediaRange instance

        Raises:
            ValueError: If value is not a string or has invalid media type format
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Expected str, got {type(value)}")

        parts = value.split(";")
        type_part = parts[0].strip()
        params = {}
        q = 1.0

        for param in parts[1:]:
            param = param.strip()
            if "=" in param:
                key, val = param.split("=", 1)
                key, val = key.strip(), val.strip()
                if key == "q":
                    q = float(val)
                else:
                    params[key] = val

        type_match = re.match(r"([^/]+)/([^/]+)", type_part)
        if not type_match:
            raise ValueError(f"Invalid media type: {type_part}")

        type_, subtype = type_match.groups()
        return cls(type=type_, subtype=subtype, parameters=params, q=q)

    def __contains__(self, pattern: Any) -> bool:
        """Implements pattern matching using the 'in' operator.

        Checks if this media range matches a given pattern.
        Handles wildcard matching (e.g., "*/*" matches anything)
        and parameter matching.

        Args:
            pattern: String or MediaRange to match against

        Returns:
            bool: True if this media range matches the pattern, False otherwise
        """
        if isinstance(pattern, str):
            pattern = MediaRange.validate(pattern)
        if isinstance(pattern, MediaRange):
            return (
                (self.type == pattern.type or self.type == "*")
                and (self.subtype == pattern.subtype or self.subtype == "*")
                and all(
                    self.parameters.get(key) == value  # pylint: disable=no-member
                    for key, value in pattern.parameters.items()
                )
            )
        return False

    def __eq__(self, other: Any) -> bool:
        """Implements equality comparison between MediaRange objects."""

        if not isinstance(other, MediaRange):
            return NotImplemented
        return (
            self.type == other.type
            and self.subtype == other.subtype
            and self.parameters == other.parameters
            and self.q == other.q
        )

    def __lt__(self, other: "MediaRange") -> bool:
        """Implements media range precedence ordering.

        Ordering is based on:
        1. Quality value (higher q values have higher precedence)
        2. Specificity (specific types have higher precedence than wildcards)
        3. Number of parameters (more parameters have higher precedence)

        Args:
            other: MediaRange to compare against

        Returns:
            bool: True if this media range has lower precedence than other
        """

        if not isinstance(other, MediaRange):
            return NotImplemented

        # Compare q-values first
        if self.q != other.q:
            return self.q < other.q

        # Then compare specificity
        if (self.type == "*") != (other.type == "*"):
            return self.type == "*"
        if (self.subtype == "*") != (other.subtype == "*"):
            return self.subtype == "*"

        # Finally compare number of parameters
        return len(self.parameters) < len(other.parameters)

    def __str__(self) -> str:
        """Returns the string representation of the media range in Accept header format."""

        parts = [f"{self.type}/{self.subtype}"]

        # Add parameters except q
        for key, value in self.parameters.items():
            parts.append(f"{key}={value}")

        # Add q-value if not default
        if self.q != 1.0:
            parts.append(f"q={self.q}")

        return ";".join(parts)

    def __hash__(self) -> int:
        """Makes MediaRange hashable for use in sets and as dict keys."""

        return hash(
            (self.type, self.subtype, frozenset(self.parameters.items()), self.q)
        )


def parse_accept_headers(value: list[str] | None) -> list[MediaRange]:
    """
    Parses and sorts HTTP Accept headers into a list of MediaRange objects.

    Args:
        value: List of Accept header strings, or None

    Returns:
        A list of MediaRange objects sorted in descending precedence order.

    Example:
        >>> parse_accept_headers(["text/html,application/xml;q=0.9"])
        [MediaRange(type='text', subtype='html', q=1.0),
         MediaRange(type='application', subtype='xml', q=0.9)]
    """

    preferences = []
    for header in value or []:
        for item in header.split(","):
            preferences.append(MediaRange.validate(item))
    return sorted(preferences, reverse=True)

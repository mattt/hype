import base64
import re
import urllib.parse
from typing import Annotated

from pydantic import StringConstraints

DATA_URL_PATTERN = r"^data:(?P<mediatype>[^,;]*)(;charset=(?P<charset>[^,;]+))?(?P<base64>;base64)?,(?P<data>.*)$"

DataUrl = Annotated[
    str, StringConstraints(pattern=DATA_URL_PATTERN, strip_whitespace=True)
]
"""
A URL containing inline data.

See https://www.rfc-editor.org/rfc/rfc2397
"""


def parse_data_url(url: DataUrl) -> tuple[str, bytes]:
    """Parses a data URL into its mediatype and decoded data content.

    Args:
        url: A data URL string conforming to RFC 2397 format. The URL should begin
            with 'data:' and contain optional mediatype, charset, and base64
            indicators followed by the data payload.

    Returns:
        A tuple containing:
            - str: The mediatype string (e.g., 'text/plain', 'image/jpeg')
            - bytes: The decoded data content

    Raises:
        ValueError: If the URL is empty or doesn't match the expected data URL format.

    Examples:
        >>> mediatype, data = parse_data_url("data:,Hello%20World!")
        >>> print(mediatype)
        'text/plain;charset=US-ASCII'
        >>> print(data)
        b'Hello World!'

        >>> mediatype, data = parse_data_url("data:text/plain;base64,SGVsbG8=")
        >>> print(mediatype)
        'text/plain'
        >>> print(data)
        b'Hello'
    """
    if not url:
        raise ValueError("Invalid data URL format")

    match = re.match(DATA_URL_PATTERN, url.strip())
    if not match:
        raise ValueError("Invalid data URL format")

    mediatype = match.group("mediatype") or "text/plain"
    charset = match.group("charset") or "US-ASCII"
    mediatype = (
        f"text/plain;charset={charset}"
        if charset and mediatype.startswith("text/")
        else mediatype
    )

    data = match.group("data")
    if match.group("base64") is not None:
        data = base64.b64decode(data)
    else:
        data = urllib.parse.unquote_to_bytes(data)

    return mediatype, data

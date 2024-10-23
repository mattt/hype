from __future__ import annotations

from collections.abc import Callable
from mimetypes import guess_type
from pathlib import Path
from typing import Annotated, cast, overload
from urllib.parse import urlparse

import httpx
from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    computed_field,
)

from .data import DataUrl, parse_data_url

HttpUrl = Annotated[
    str, StringConstraints(pattern=r"^https?://", strip_whitespace=True)
]
"""
A URL pointing to a remote file.
"""

Loader = Annotated[
    Callable[[HttpUrl], "File"],
    "A callable that takes an HTTP URL and returns a File.",
]


class File(BaseModel):
    """A class representing a file with its content and metadata.

    This class provides methods to create File objects from various sources
    including bytes, paths, URLs, and other File objects.
    It handles both local and remote files,
    supporting HTTP(S) URLs and data URLs.
    """

    content_type: str | None = Field(None, examples=["application/zip"])
    """The MIME type of the file."""

    name: str | None = Field(None, examples=["archive.zip"])
    """The name of the file."""

    data: bytes = Field(None, exclude=True, repr=False)
    """The contents of the file."""

    @computed_field
    @property
    def size(self) -> int:
        """Returns the size of the file in bytes."""
        return len(self.data)

    @classmethod
    def from_file(
        cls,
        file: File,
        content_type: str | None = None,
        name: str | None = None,
    ) -> File:
        """
        Load a file from another file.

        Args:
            file: The file to load the data from.
            content_type: The MIME type of the file.
            name: The name of the file.

        Returns:
            A File object.
        """

        return cls(
            content_type=content_type or file.content_type,
            name=name or file.name,
            data=file.data,
        )

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        content_type: str | None = None,
        name: str | None = None,
    ) -> File:
        """
        Load a file from bytes.

        Args:
            data: The bytes to load the file from.
            content_type: The MIME type of the file.
            name: The name of the file.

        Returns:
            A File object.
        """

        if content_type is None and name is not None:
            content_type, _ = guess_type(name or "")

        return cls(content_type=content_type, name=name, data=data)

    @classmethod
    def from_path(
        cls,
        path: Path | str,
        content_type: str | None = None,
        name: str | None = None,
    ) -> File:
        """
        Load a file from a local path.

        Args:
            path: The path to the file.
            content_type: The MIME type of the file.
            name: The name of the file.

        Returns:
            A File object.
        """

        with open(path, "rb") as file:
            data = file.read()

        return cls(content_type=content_type, name=name, data=data)

    @overload
    @classmethod
    def from_url(
        cls,
        url: DataUrl,
        *,
        content_type: str | None = None,
        name: str | None = None,
    ) -> File: ...

    @overload
    @classmethod
    def from_url(
        cls,
        url: HttpUrl,
        *,
        loader: Loader,
        content_type: str | None = None,
        name: str | None = None,
    ) -> File: ...

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        loader: Loader | None = None,
        content_type: str | None = None,
        name: str | None = None,
    ) -> File:
        """
        Load a file from a URL.

        Args:
            url: The URL to load the file from.
            loader: A callable that takes an HTTP URL and returns a File.
                Only required for HTTP(S) URLs.
            content_type: The MIME type of the file.
            name: The name of the file.

        Returns:
            A File object.
        """

        def default_loader(http_url: HttpUrl) -> File:
            response = httpx.get(http_url)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type")

            content_disposition = response.headers.get("Content-Disposition")
            name = None
            if content_disposition:
                disposition_parts = content_disposition.split(";")
                for part in disposition_parts:
                    if part.strip().startswith("filename="):
                        name = part.split("=")[1].strip().strip('"')
                        break
            return cls.from_bytes(
                response.content, content_type=content_type, name=name
            )

        parsed = urlparse(url.strip())

        if parsed.scheme == "data":
            content_type, data = parse_data_url(url)
            return cls(content_type=content_type, name=name, data=data)

        if parsed.scheme in ("http", "https"):
            if loader is None or loader is ...:
                loader = default_loader
            return loader(cast(HttpUrl, url))

        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

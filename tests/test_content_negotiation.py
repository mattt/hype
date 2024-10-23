import base64
import json
from typing import Annotated

import pytest
from fastapi import FastAPI, Header, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.testclient import TestClient

from hype.http.accept import MediaRange, parse_accept_headers


def test_media_range_validation():
    # Basic media types
    media = MediaRange.validate("text/plain")
    assert media.type == "text"
    assert media.subtype == "plain"

    # With parameters
    media = MediaRange.validate("text/plain; charset=utf-8; format=compact")
    assert media.parameters == {"charset": "utf-8", "format": "compact"}

    # With q-value
    media = MediaRange.validate("text/plain;q=0.8")
    assert media.q == 0.8

    # Invalid formats
    with pytest.raises(ValueError):
        MediaRange.validate("invalid")
    with pytest.raises(ValueError):
        MediaRange.validate("text")
    with pytest.raises(ValueError):
        MediaRange.validate("text/")


def test_media_range_matching():
    # Exact matches
    assert "text/plain" in MediaRange.validate("text/plain")
    assert "text/plain; charset=utf-8" in MediaRange.validate(
        "text/plain; charset=utf-8"
    )

    # Wildcard matches
    assert "text/plain" in MediaRange.validate("*/*")
    assert "text/plain" in MediaRange.validate("text/*")

    # Parameter matching
    media = MediaRange.validate("text/plain; charset=utf-8")
    assert "text/plain" in media
    assert "text/plain; charset=ascii" not in media

    # Non-matches
    assert "image/png" not in MediaRange.validate("text/plain")
    assert "text/html" not in MediaRange.validate("text/plain")


def test_media_range_ordering():
    # Test complete ordering
    ranges = [
        MediaRange.validate(value)
        for value in [
            "*/*; q=0.1",
            "*/*; q=0.5",
            "text/*; q=0.5",
            "text/plain; q=0.5",
            "text/plain; q=0.8",
            "*/*",
            "text/*",
            "text/plain",
            "text/plain; charset=ascii",
            "text/plain; charset=utf-8",
            "text/plain; charset=utf-8; format=compact",
        ]
    ]
    assert sorted(ranges) == ranges  # Verify complete ordering


def test_parse_accept_headers():
    headers = ["text/plain, text/html;q=0.8, */*;q=0.1"]
    preferences = parse_accept_headers(headers)

    assert len(preferences) == 3
    assert preferences[0].type == "text"
    assert preferences[0].subtype == "plain"
    assert preferences[0].q == 1.0

    assert preferences[1].type == "text"
    assert preferences[1].subtype == "html"
    assert preferences[1].q == 0.8

    assert preferences[2].type == "*"
    assert preferences[2].subtype == "*"
    assert preferences[2].q == 0.1

    # Empty or None input
    assert parse_accept_headers([]) == []
    assert parse_accept_headers(None) == []


def test_negotiate_text_response():
    app = FastAPI()

    @app.post("/greet")
    def greet(
        accept: Annotated[list[str] | None, Header()] = None,
    ) -> Response:
        for preference in parse_accept_headers(accept):
            if "text/plain; format=compact" in preference:
                return PlainTextResponse(status_code=201, content="Hi!")
            if "text/plain" in preference:
                return PlainTextResponse(status_code=201, content="Hello, world!")

        return JSONResponse(status_code=406, content={"message": "Not Acceptable"})

    client = TestClient(app)

    response = client.post("/greet", headers={"Accept": "text/plain;format=compact"})
    assert response.status_code == 201
    assert response.text == "Hi!"

    response = client.post("/greet", headers={"Accept": "text/plain;charset=utf-8"})
    assert response.status_code == 201
    assert response.text == "Hello, world!"

    response = client.post("/greet", headers={"Accept": "text/plain"})
    assert response.status_code == 201
    assert response.text == "Hello, world!"

    response = client.post("/greet", headers={"Accept": "text/plain"})
    assert response.status_code == 201
    assert response.text == "Hello, world!"

    response = client.post("/greet", headers={"Accept": "*/*"})
    assert response.status_code == 201
    assert response.text == "Hello, world!"

    client.post("/greet", headers={})
    assert response.status_code == 201
    assert response.text == "Hello, world!"

    with pytest.raises(ValueError):
        client.post("/greet", headers={"Accept": ""})

    response = client.post("/greet", headers={"Accept": "image/png"})
    assert response.status_code == 406
    assert response.json() == {"message": "Not Acceptable"}


def test_negotiate_image_response():
    image_data = {
        "webp": b"WEBP_IMAGE_DATA",
        "png": b"PNG_IMAGE_DATA",
        "jpeg": b"JPEG_IMAGE_DATA",
    }

    image_metadata = {
        "width": 1920,
        "height": 1080,
        "quality": 85,
    }

    app = FastAPI()

    @app.post("/generate")
    def generate(
        accept: Annotated[list[str] | None, Header()] = None,
    ) -> Response:
        for preference in parse_accept_headers(accept):
            if "image/webp; disposition=inline" in preference:
                data = base64.b64encode(image_data["webp"]).decode("utf-8")
                return Response(
                    content=f"data:image/webp;base64,{data}",
                    media_type="text/uri-list",
                    headers={"Content-Disposition": "inline; filename=image.webp"},
                )
            elif "image/webp" in preference:
                return Response(
                    content=image_data["webp"],
                    media_type="image/webp",
                    headers={"Content-Disposition": "attachment; filename=image.webp"},
                )
            elif "image/png" in preference:
                return Response(
                    content=image_data["png"],
                    media_type="image/png",
                    headers={"Content-Disposition": "attachment; filename=image.png"},
                )
            elif "image/jpeg" in preference:
                return Response(
                    content=image_data["jpeg"],
                    media_type="image/jpeg",
                    headers={"Content-Disposition": "attachment; filename=image.jpeg"},
                )
            elif "multipart/related+webp" in preference:
                boundary = "boundary"
                body = (
                    (
                        f"--{boundary}\r\n"
                        f'Content-Disposition: form-data; name="metadata"\r\n'
                        f"Content-Type: application/json\r\n\r\n"
                        f"{json.dumps(image_metadata)}\r\n"
                        f"--{boundary}\r\n"
                        f'Content-Disposition: form-data; name="image"; filename="image.webp"\r\n'
                        f"Content-Type: image/webp\r\n\r\n"
                    ).encode()
                    + image_data["webp"]
                    + f"\r\n--{boundary}--".encode()
                )
                return Response(
                    content=body,
                    media_type=f"multipart/related; boundary={boundary}",
                    headers={"Content-Type": f"multipart/related; boundary={boundary}"},
                )

        return JSONResponse(status_code=406, content={"message": "Not Acceptable"})

    client = TestClient(app)

    response = client.post("/generate", headers={"Accept": "image/webp"})
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/webp"
    assert response.content == image_data["webp"]

    response = client.post("/generate", headers={"Accept": "image/png"})
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/png"
    assert response.headers["Content-Disposition"] == "attachment; filename=image.png"
    assert response.content == image_data["png"]

    response = client.post("/generate", headers={"Accept": "image/jpeg"})
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/jpeg"
    assert response.content == image_data["jpeg"]

    response = client.post(
        "/generate", headers={"Accept": "image/webp; disposition=inline"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/uri-list; charset=utf-8"
    assert response.headers["Content-Disposition"] == "inline; filename=image.webp"
    assert response.text.startswith("data:image/webp;base64,")
    assert base64.b64decode(response.text.split(",")[1]) == image_data["webp"]

    response = client.post("/generate", headers={"Accept": "multipart/related+webp"})
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("multipart/related; boundary=")

    response = client.post("/generate", headers={"Accept": "*/*"})
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/webp"
    assert response.content == image_data["webp"]

    with pytest.raises(ValueError):
        client.post("/generate", headers={"Accept": ""})

    response = client.post("/generate", headers={"Accept": "image/bmp"})
    assert response.status_code == 406
    assert response.json() == {"message": "Not Acceptable"}

from typing import Annotated

import pytest
from fastapi import FastAPI, Header, Response
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from hype.http.prefer import RequestPreferences, parse_prefer_headers


def test_parse_empty_header():
    header = ""
    prefs = RequestPreferences.parse(header)
    assert prefs == RequestPreferences()


def test_none_header():
    header = None
    prefs = RequestPreferences.parse(header)
    assert prefs == RequestPreferences()


def test_empty_header():
    header = ""
    prefs = RequestPreferences.parse(header)
    assert prefs == RequestPreferences()


def test_invalid_header():
    header = "invalid"
    with pytest.raises(ValueError):
        RequestPreferences.parse(header)


def test_respond_async():
    header = "respond-async"
    prefs = RequestPreferences.parse(header)

    assert prefs.respond_async

    assert prefs.wait is None
    assert prefs.handling is None
    assert prefs.return_ is None


def test_return_representation():
    header = "return=representation"
    prefs = RequestPreferences.parse(header)

    assert prefs.return_ == "representation"

    assert prefs.respond_async is None
    assert prefs.wait is None
    assert prefs.handling is None


def test_return_minimal():
    header = "return=minimal"
    prefs = RequestPreferences.parse(header)

    assert prefs.return_ == "minimal"

    assert prefs.respond_async is None
    assert prefs.wait is None
    assert prefs.handling is None


def test_wait():
    header = "wait=100"
    prefs = RequestPreferences.parse(header)

    assert prefs.wait == 100

    assert prefs.respond_async is None
    assert prefs.handling is None
    assert prefs.return_ is None


def test_handling_strict():
    header = "handling=strict"
    prefs = RequestPreferences.parse(header)

    assert prefs.handling == "strict"

    assert prefs.respond_async is None
    assert prefs.wait is None
    assert prefs.return_ is None


def test_handling_lenient():
    header = "handling=lenient"
    prefs = RequestPreferences.parse(header)

    assert prefs.handling == "lenient"

    assert prefs.respond_async is None
    assert prefs.wait is None
    assert prefs.return_ is None


def test_multiple_preferences():
    header = "respond-async, wait=100, handling=lenient, return=representation"
    prefs = RequestPreferences.parse(header)

    assert prefs.respond_async
    assert prefs.wait == 100
    assert prefs.handling == "lenient"
    assert prefs.return_ == "representation"


def test_case_insensitive():
    header = "RETURN=minimal, RESPOND-ASYNC"
    prefs = RequestPreferences.parse(header)

    assert prefs.respond_async
    assert prefs.return_ == "minimal"


def test_invalid_return_value():
    header = "return=invalid"
    with pytest.raises(ValueError):
        RequestPreferences.parse(header)


def test_invalid_wait_value():
    header = "wait=notanumber"
    with pytest.raises(ValueError):
        RequestPreferences.parse(header)


def test_invalid_handling_value():
    header = "handling=invalid"
    with pytest.raises(ValueError):
        RequestPreferences.parse(header)


def test_basic_preferences():
    app = FastAPI()

    @app.post("/tasks")
    def create_task(
        prefer: Annotated[list[str] | None, Header()] = None,
    ) -> Response:
        prefs = parse_prefer_headers(prefer)

        # Simulate async processing
        if prefs.respond_async:
            return Response(
                status_code=202,
                headers={"Location": "/tasks/123", "Retry-After": "5"},
            )

        # Handle return preference
        if prefs.return_ == "minimal":
            return Response(
                status_code=201,
                headers={"Location": "/tasks/123"},
            )

        # Default to full representation
        return JSONResponse(
            status_code=201,
            content={"id": "123", "status": "pending"},
            headers={"Location": "/tasks/123"},
        )

    client = TestClient(app)

    # Test async preference
    response = client.post("/tasks", headers={"Prefer": "respond-async"})
    assert response.status_code == 202
    assert response.headers["Location"] == "/tasks/123"
    assert response.headers["Retry-After"] == "5"

    # Test minimal return
    response = client.post("/tasks", headers={"Prefer": "return=minimal"})
    assert response.status_code == 201
    assert response.headers["Location"] == "/tasks/123"
    assert not response.content  # Should be empty

    # Test full representation (default)
    response = client.post("/tasks", headers={"Prefer": "return=representation"})
    assert response.status_code == 201
    assert response.headers["Location"] == "/tasks/123"
    assert response.json() == {"id": "123", "status": "pending"}


def test_handling_preferences():
    app = FastAPI()

    @app.post("/users")
    def create_user(
        prefer: Annotated[list[str] | None, Header()] = None,
    ) -> Response:
        prefs = parse_prefer_headers(prefer)

        # Simulate a partial success scenario
        if prefs.handling == "lenient":
            return JSONResponse(
                status_code=201,
                content={
                    "id": "456",
                    "warnings": ["Some optional fields were ignored"],
                },
                headers={"Preference-Applied": "handling=lenient"},
            )
        elif prefs.handling == "strict":
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid optional fields"},
            )

        # Default to strict handling
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid optional fields"},
        )

    client = TestClient(app)

    # Test lenient handling
    response = client.post("/users", headers={"Prefer": "handling=lenient"})
    assert response.status_code == 201
    assert response.headers["Preference-Applied"] == "handling=lenient"
    assert response.json()["warnings"] == ["Some optional fields were ignored"]

    # Test strict handling
    response = client.post("/users", headers={"Prefer": "handling=strict"})
    assert response.status_code == 400
    assert response.json()["error"] == "Invalid optional fields"


def test_wait_preference():
    app = FastAPI()

    @app.post("/process")
    def process(
        prefer: Annotated[list[str] | None, Header()] = None,
    ) -> Response:
        prefs = parse_prefer_headers(prefer)

        # Simulate a long-running process
        if prefs.wait is not None and prefs.wait < 10:
            return JSONResponse(
                status_code=202,
                content={
                    "message": "Processing will take longer than requested wait time"
                },
                headers={
                    "Retry-After": "10",
                    "Preference-Applied": f"wait={prefs.wait}",
                },
            )

        return JSONResponse(
            status_code=200,
            content={"status": "completed"},
            headers={"Preference-Applied": f"wait={prefs.wait}"},
        )

    client = TestClient(app)

    # Test short wait time
    response = client.post("/process", headers={"Prefer": "wait=5"})
    assert response.status_code == 202
    assert response.headers["Preference-Applied"] == "wait=5"
    assert response.headers["Retry-After"] == "10"

    # Test acceptable wait time
    response = client.post("/process", headers={"Prefer": "wait=15"})
    assert response.status_code == 200
    assert response.headers["Preference-Applied"] == "wait=15"
    assert response.json()["status"] == "completed"

import json
from typing import Annotated, cast

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import Field

import hype
from hype import create_fastapi_app


def test_app_with_empty_functions():
    app = create_fastapi_app([])
    with TestClient(app) as client:
        assert app is not None
        assert isinstance(app, FastAPI)

        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert "3" in response.json()["openapi"]


def test_app_with_single_function():
    @hype.up
    def add(x: int, y: int) -> int:
        return x + y

    app = create_fastapi_app([add])
    with TestClient(app) as client:
        assert app is not None
        assert isinstance(app, FastAPI)

        if route := next(
            (r for r in cast(list[APIRoute], app.routes) if r.path == "/add"), None
        ):
            assert route.methods == {"POST"}
            assert route.name == "add"
        else:
            pytest.fail("Route not found: /add")

        response = client.post("/add", json={"x": 1, "y": 2})
        assert response.status_code == 200
        assert response.json() == 3


def test_app_with_multiple_functions():
    @hype.up
    def add(x: int, y: int) -> int:
        return x + y

    @hype.up
    def multiply(x: int, y: int) -> int:
        return x * y

    @hype.up
    def abs(x: int) -> int:
        return x if x > 0 else -x

    app = create_fastapi_app([add, multiply, abs])
    with TestClient(app) as client:
        assert app is not None
        assert isinstance(app, FastAPI)

        if route := next(
            (r for r in cast(list[APIRoute], app.routes) if r.path == "/add"), None
        ):
            assert route.methods == {"POST"}
            assert route.name == "add"
        else:
            pytest.fail("Route not found: /add")

        if route := next(
            (r for r in cast(list[APIRoute], app.routes) if r.path == "/multiply"), None
        ):
            assert route.methods == {"POST"}
            assert route.name == "multiply"
        else:
            pytest.fail("Route not found: /multiply")

        if route := next(
            (r for r in cast(list[APIRoute], app.routes) if r.path == "/abs"), None
        ):
            assert route.methods == {"POST"}
            assert route.name == "abs"
        else:
            pytest.fail("Route not found: /abs")

        response = client.post("/add", json={"x": 1, "y": 2})
        assert response.status_code == 200
        assert response.json() == 3

        response = client.post("/multiply", json={"x": 2, "y": 3})
        assert response.status_code == 200
        assert response.json() == 6

        response = client.post("/abs", json={"x": -1})
        assert response.status_code == 200
        assert response.json() == 1

        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        print(json.dumps(schema, indent=2))
        operation = schema["paths"]["/add"]["post"]
        assert operation["operationId"] == "add"

        input = schema["components"]["schemas"]["add_Input"]
        assert input["properties"]["x"]["type"] == "integer"
        assert input["properties"]["y"]["type"] == "integer"

        output = schema["components"]["schemas"]["add_Output"]
        assert output["type"] == "integer"


def test_app_with_function_with_rest_docstring():
    @hype.up
    def subtract(x: int, y: int) -> int:
        """
        Subtracts two numbers
        :param x: The first number
        :param y: The second number
        :return: The result of the subtraction
        """
        return x - y

    app = create_fastapi_app([subtract])
    with TestClient(app) as client:
        assert app is not None
        assert isinstance(app, FastAPI)

        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        operation = schema["paths"]["/subtract"]["post"]
        assert operation["operationId"] == "subtract"
        assert "Subtracts two numbers" in operation["summary"]

        input = schema["components"]["schemas"]["subtract_Input"]
        assert input["properties"]["x"]["type"] == "integer"
        assert input["properties"]["x"]["description"] == "The first number"
        assert input["properties"]["y"]["type"] == "integer"
        assert input["properties"]["y"]["description"] == "The second number"

        output = schema["components"]["schemas"]["subtract_Output"]
        assert output["type"] == "integer"
        assert output["description"] == "The result of the subtraction"


def test_app_with_function_numpy_style_docstring():
    @hype.up
    def increment(x: int) -> int:
        """
        Increments a number by 1.

        Parameters
        ----------
        x : int
            The number to increment.

        Returns
        -------
        int
            The incremented value.
        """
        return x + 1

    app = create_fastapi_app([increment])
    with TestClient(app) as client:
        assert app is not None
        assert isinstance(app, FastAPI)

        response = client.get("/openapi.json")
        schema = response.json()
        operation = schema["paths"]["/increment"]["post"]

        assert operation["summary"] == "Increments a number by 1."
        assert (
            schema["components"]["schemas"]["increment_Input"]["properties"]["x"][
                "description"
            ]
            == "The number to increment."
        )
        assert (
            schema["components"]["schemas"]["increment_Output"]["description"]
            == "The incremented value."
        )


def test_app_with_function_epydoc_style_docstring():
    @hype.up
    def negate(x: int) -> int:
        """
        Negates a number.

        @param x: The number to negate.
        @type x: int
        @return: The negated value.
        @rtype: int
        """
        return -x

    app = create_fastapi_app([negate])
    with TestClient(app) as client:
        assert app is not None
        assert isinstance(app, FastAPI)

        response = client.get("/openapi.json")
        schema = response.json()
        operation = schema["paths"]["/negate"]["post"]

        assert operation["summary"] == "Negates a number."
        assert (
            schema["components"]["schemas"]["negate_Input"]["properties"]["x"][
                "description"
            ]
            == "The number to negate."
        )
        assert (
            schema["components"]["schemas"]["negate_Output"]["description"]
            == "The negated value."
        )


def test_app_with_function_google_style_docstring():
    @hype.up
    def decrement(x: int) -> int:
        """Decrements a number by 1.

        Args:
            x: The number to decrement.

        Returns:
            The decremented value.
        """
        return x - 1

    app = create_fastapi_app([decrement])
    with TestClient(app) as client:
        assert app is not None
        assert isinstance(app, FastAPI)

        response = client.get("/openapi.json")
        schema = response.json()
        operation = schema["paths"]["/decrement"]["post"]

        assert operation["summary"] == "Decrements a number by 1."
        assert (
            schema["components"]["schemas"]["decrement_Input"]["properties"]["x"][
                "description"
            ]
            == "The number to decrement."
        )
        assert (
            schema["components"]["schemas"]["decrement_Output"]["description"]
            == "The decremented value."
        )


def test_app_with_function_with_docstring_and_field_info():
    @hype.up
    def divide(
        x: int = Field(..., description="The dividend"),
        y: int = Field(..., description="The divisor", gt=0),
    ) -> Annotated[int, Field(description="The quotient")]:
        """
        Divides two numbers
        :param x: (This description is overwritten by the field info)
        :param y: (This description is overwritten by the field info)
        :return: (This description is overwritten by the field info)
        """
        return x // y

    app = create_fastapi_app([divide])
    with TestClient(app) as client:
        assert app is not None
        assert isinstance(app, FastAPI)

        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        operation = schema["paths"]["/divide"]["post"]
        assert operation["operationId"] == "divide"
        assert "Divides two numbers" in operation["summary"]

        input = schema["components"]["schemas"]["divide_Input"]
        assert input["properties"]["x"]["type"] == "integer"
        assert input["properties"]["x"]["description"] == "The dividend"
        assert input["properties"]["y"]["type"] == "integer"
        assert input["properties"]["y"]["description"] == "The divisor"

        output = schema["components"]["schemas"]["divide_Output"]
        assert output["type"] == "integer"
        assert output["description"] == "The quotient"


def test_app_with_function_that_raises_exception():
    class CustomError(Exception):
        pass

    @hype.up
    def fail() -> None:
        """Intentionally raises an exception"""
        raise CustomError("Something went wrong")

    app = create_fastapi_app([fail])
    with TestClient(app) as client:
        response = client.post("/fail", json={})

        assert response.status_code == 500
        assert response.headers["content-type"] == "application/problem+json"

        problem = response.json()
        assert problem["status"] == 500
        assert problem["title"] == "Application Error"
        assert problem["detail"] == "Something went wrong"

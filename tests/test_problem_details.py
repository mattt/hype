from typing import Annotated

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import AnyUrl, BaseModel, ValidationError

from hype.http.problem import Problem, ProblemResponse, problem_exception_handler


def test_problem_default_values():
    problem = Problem()
    assert problem.type == "about:blank"
    assert problem.title is None
    assert problem.status is None
    assert problem.detail is None
    assert problem.instance is None


def test_problem_with_values():
    problem = Problem(
        type=AnyUrl("https://example.com/problems/out-of-stock"),
        title="Out of Stock",
        status=400,
        detail="The requested item is currently out of stock.",
        instance="/orders/12345",
    )
    assert str(problem.type) == "https://example.com/problems/out-of-stock"
    assert problem.title == "Out of Stock"
    assert problem.status == 400
    assert problem.detail == "The requested item is currently out of stock."
    assert problem.instance == "/orders/12345"


def test_problem_type_validation():
    with pytest.raises(ValidationError):
        Problem(type=AnyUrl("not a valid URL"))


def test_problem_status_validation():
    with pytest.raises(ValidationError):
        Problem(status=99)

    with pytest.raises(ValidationError):
        Problem(status=600)


def test_problem_instance_validation():
    with pytest.raises(ValidationError):
        Problem(instance="not a valid URL")


def test_problem_extra_fields():
    problem = Problem(extra_field="This is allowed")  # type: ignore
    assert problem.extra_field == "This is allowed"  # type: ignore


def test_problem_parse_method():
    data = {
        "type": "https://example.com/problems/insufficient-funds",
        "title": "Insufficient Funds",
        "status": 403,
        "detail": "Your account does not have enough funds to complete this transaction.",
        "instance": "/transactions/12345",
        "balance": 30.5,
    }
    problem = Problem.validate(data)
    assert str(problem.type) == "https://example.com/problems/insufficient-funds"
    assert problem.title == "Insufficient Funds"
    assert problem.status == 403
    assert (
        problem.detail
        == "Your account does not have enough funds to complete this transaction."
    )
    assert problem.instance == "/transactions/12345"
    assert problem.balance == 30.5  # type: ignore


def test_problem_type_default():
    problem = Problem(type=None)  # type: ignore
    assert str(problem.type) == "about:blank"


def test_problem_populate_by_name():
    problem = Problem(**{"type": "https://example.com/problem", "status": 404})
    assert str(problem.type) == "https://example.com/problem"
    assert problem.status == 404


def test_problem_response_integration():
    class Item(BaseModel):
        name: str
        quantity: int

    app = FastAPI()
    app.add_exception_handler(ValueError, problem_exception_handler)
    app.add_exception_handler(HTTPException, problem_exception_handler)
    app.add_exception_handler(RequestValidationError, problem_exception_handler)

    items = [
        {"name": "banana", "quantity": 1},
        {"name": "apple", "quantity": 2},
    ]

    @app.post("/items", response_model=None)
    def create_item(
        item: Item,
        accept: Annotated[list[str] | None, Header()] = None,  # pylint: disable=unused-argument
    ) -> JSONResponse | ProblemResponse:
        if item.quantity < 0:
            return ProblemResponse(
                content=Problem(
                    type="https://example.com/problems/invalid-quantity",
                    title="Invalid Quantity",
                    status=400,
                    detail="Item quantity cannot be negative",
                    instance="/items",
                    received_quantity=item.quantity,  # type: ignore
                )
            )
        obj = item.model_dump()
        items.append(obj)
        return JSONResponse(content=obj)

    @app.get("/items/{item_id}", response_model=None)
    def get_item(item_id: int) -> JSONResponse | ProblemResponse:
        if item_id < 1:  # Changed from 0 to 1
            return ProblemResponse(
                content=Problem(
                    type="https://example.com/problems/invalid-id",
                    title="Invalid Item ID",
                    status=400,
                    detail="Item ID cannot be negative or zero",  # Updated message
                    instance=f"/items/{item_id}",
                )
            )
        try:
            return JSONResponse(content=items[item_id - 1])  # Adjust index by -1
        except IndexError:
            raise HTTPException(status_code=404, detail="Item not found")

    client = TestClient(app)

    # Test custom problem response
    response = client.get("/items/-1")
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "https://example.com/problems/invalid-id",
        "title": "Invalid Item ID",
        "status": 400,
        "detail": "Item ID cannot be negative or zero",
        "instance": "/items/-1",
    }

    # Test general exception handler
    response = client.get("/items/1")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"name": "banana", "quantity": 1}

    # Test HTTP exception handler
    response = client.get("/items/100")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "status": 404,
        "detail": "Item not found",
    }

    # Test validation error with custom fields
    response = client.post(
        "/items",
        json={"name": "apple", "quantity": -5},
    )
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["type"] == "https://example.com/problems/invalid-quantity"
    assert problem["title"] == "Invalid Quantity"
    assert problem["status"] == 400
    assert problem["detail"] == "Item quantity cannot be negative"
    assert problem["instance"] == "/items"
    assert problem["received_quantity"] == -5

    # Test successful request
    response = client.post(
        "/items",
        json={"name": "orange", "quantity": 5},
    )
    assert response.status_code == 200
    assert response.json() == {"name": "orange", "quantity": 5}

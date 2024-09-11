from typing import (
    Literal,
)

import pydantic
import pytest

from hype.function import export


@export
def f(
    x: Literal[1, 2, 3],
    y: int = pydantic.Field(..., description="The second number (from field)"),
) -> int:
    """
    Returns the sum of two numbers.

    :param x: The first number
    :param y: The second number (from docstring)
    :return: The sum of the two numbers
    """

    return x + y


def test_function_wrapper():
    # Test valid inputs
    assert f(1, 2) == 3
    assert f(x=2, y=3) == 5

    # Test invalid inputs
    with pytest.raises(pydantic.ValidationError):
        f(4, 5)  # 4 is not in Literal[1, 2, 3] # type: ignore

    with pytest.raises(pydantic.ValidationError):
        f(1, "two")  # "two" is not an int # type: ignore


def test_function_schema():
    schema = f.json_schema

    assert schema["title"] == "f"
    assert "Input" in schema["$defs"]
    assert "Output" in schema["$defs"]

    input_props = schema["$defs"]["Input"]["properties"]
    assert set(input_props.keys()) == {"x", "y"}
    assert input_props["x"]["enum"] == [1, 2, 3]
    assert input_props["y"]["type"] == "integer"

    assert schema["$defs"]["Output"]["type"] == "integer"


def test_function_input_output_models():
    assert f.input.__name__ == "Input"
    assert set(f.input.model_fields.keys()) == {"x", "y"}

    assert f.output.__name__ == "Output"
    assert set(f.output.model_fields.keys()) == {"root"}


def test_function_docstring_description():
    schema = f.json_schema

    input_props = schema["$defs"]["Input"]["properties"]
    assert input_props["x"]["description"] == "The first number"
    assert input_props["y"]["description"] == "The second number (from field)"

    assert schema["$defs"]["Output"]["description"] == "The sum of the two numbers"

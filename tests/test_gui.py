from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

import gradio as gr
import pytest
from pydantic import BaseModel, Field

import hype
from hype.gui.gradio import create_gradio_component, create_gradio_interface


# Test Models and Enums
class Color(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


HttpStatus = Enum(
    "HttpStatus",
    {
        "OK": 200,
        "CREATED": 201,
        "ACCEPTED": 202,
        "BAD_REQUEST": 400,
        "UNAUTHORIZED": 401,
        "FORBIDDEN": 403,
        "NOT_FOUND": 404,
        "SERVER_ERROR": 500,
        "BAD_GATEWAY": 502,
        "SERVICE_UNAVAILABLE": 503,
    },
)


class InputModel(BaseModel):
    text: str = Field(description="A simple text field")
    number: int = Field(description="An unbounded number")
    percent: int = Field(gt=0, lt=100, description="A number between 0 and 100")
    radio: Color = Field(description="Choose a color")
    dropdown: HttpStatus = Field(description="Choose an HTTP status code")
    date: datetime = Field(description="Pick a date")
    files: list[Path] = Field(description="Upload multiple files")
    optional: str | None = None
    config: dict[str, str] = Field(default_factory=dict)
    long_text: str = Field(description="A long text field", min_length=100)
    decimal: Decimal = Field(description="A decimal number", decimal_places=2)


class OutputModel(BaseModel):
    result: str
    count: int


@hype.up
def example(
    text: str,
    number: int = Field(gt=0, lt=100),
    choice: Color = Color.RED,
) -> str:
    """Test function with various input types.

    Args:
        text: A test string
        number: A number between 0 and 100
        choice: Color choice

    Returns:
        A formatted string with the inputs
    """
    return f"{text} - {number} - {choice.value}"


@pytest.fixture
def interface():
    return create_gradio_interface(example)


@pytest.mark.filterwarnings("ignore:There is no current event loop:DeprecationWarning")
@pytest.mark.asyncio
async def test_interface_creation(interface):
    assert isinstance(interface, gr.Interface)
    assert interface.title == "example"
    assert len(interface.input_components) == 3
    assert len(interface.output_components) == 3  # result + JSON + error


@pytest.mark.parametrize(
    "field_name,field_type,expected_type",
    [
        ("text", str, gr.Textbox),
        ("number", int, gr.Number),
        ("percent", int, gr.Slider),
        ("radio", Color, gr.Radio),
        ("dropdown", int, gr.Dropdown),
        ("date", datetime, gr.DateTime),
        ("files", list[Path], gr.File),
        ("config", dict[str, str], gr.JSON),
        ("long_text", str, gr.Textbox),
        ("decimal", Decimal, gr.Number),
    ],
)
def test_component_creation(field_name, field_type, expected_type):
    model = InputModel
    field_info = model.model_fields[field_name]
    component = create_gradio_component(field_name, field_info)
    if not isinstance(component, expected_type):
        raise AssertionError(f"Expected {expected_type}, got {type(component)}")


def test_interface_validation(interface):
    # Test valid input
    result = interface.fn("test", 50, Color.RED)
    assert result[0] == "test - 50 - red"
    assert result[1] == "test - 50 - red"
    assert not result[2]["visible"]

    # Test invalid input (should return validation error)
    result = interface.fn("test", -1, Color.RED)
    assert all(r is None for r in result[:-1])
    assert result[-1]["visible"]
    assert "Validation Errors" in result[-1]["value"]


def test_optional_fields():
    @hype.up
    def optional_func(text: str | None = None) -> str:
        return text or "default"

    interface = create_gradio_interface(optional_func)
    assert len(interface.input_components) == 1
    assert isinstance(interface.input_components[0], gr.Textbox)

    # Test with and without input
    assert interface.fn(None)[0] == "default"
    assert interface.fn("test")[0] == "test"


def test_complex_output():
    @hype.up
    def complex_output() -> OutputModel:
        return OutputModel(result="test", count=42)

    interface = create_gradio_interface(complex_output)
    assert len(interface.output_components) == 4  # result + count + JSON + error

    result = interface.fn()
    assert result[0] == "test"  # result field
    assert result[1] == 42  # count field
    assert result[2] == {"result": "test", "count": 42}  # JSON output
    assert not result[3]["visible"]


def test_error_handling():
    @hype.up
    def error_func(x: int) -> int:
        raise ValueError("Test error")

    interface = create_gradio_interface(error_func)
    result = interface.fn(1)

    assert all(r is None for r in result[:-1])
    assert result[-1]["visible"]
    assert "ValueError" in result[-1]["value"]
    assert "Test error" in result[-1]["value"]

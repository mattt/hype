from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo
from pydantic.networks import IPvAnyAddress, IPvAnyInterface, IPvAnyNetwork
from pydantic.types import (
    ByteSize,
    Decimal,
    PathType,
)
from pydantic_core import PydanticUndefinedType

from hype.function import Function

if TYPE_CHECKING:
    import gradio as gr


def create_gradio_component(
    name: str, field_info: FieldInfo, **kwargs: Any
) -> "gr.Component":
    import gradio as gr

    label = field_info.alias or name

    field_type = field_info.annotation
    if get_origin(field_type) is Union:
        # Handle Optional types
        args = get_args(field_type)
        if len(args) == 2 and type(None) in args:
            field_type = next(arg for arg in args if arg is not type(None))

    default = (
        None
        if field_info.default_factory is not None
        or isinstance(field_info.default, PydanticUndefinedType)
        else field_info.default
    )

    json_schema_extra = getattr(field_info, "json_schema_extra", {}) or {}

    # Handle IP addresses
    if field_type in (
        IPvAnyAddress,
        IPvAnyInterface,
        IPvAnyNetwork,
    ):
        return gr.Textbox(
            label=label,
            info=field_info.description,
            placeholder=f"Enter valid {field_type.__name__}",
            **kwargs,
        )

    # Handle lists/sequences
    if get_origin(field_type) in (list, tuple, set):
        inner_type = get_args(field_type)[0]
        if inner_type in (str, int, float):
            return gr.Dropdown(
                multiselect=True,
                label=label,
                info=field_info.description,
                allow_custom_value=True,
                value=field_info.default
                if field_info.default_factory is None
                else None,
                **kwargs,
            )
        elif inner_type is Path:
            return gr.File(
                label=label,
                file_count="multiple",
                **kwargs,
            )

    # Handle dictionaries
    if get_origin(field_type) is dict:
        return gr.JSON(
            label=label,
            **kwargs,
        )

    # Handle datetime types
    if field_type is datetime:
        return gr.DateTime(
            label=label,
            value=default,
            info=field_info.description,
            **kwargs,
        )

    # Handle file paths and URLs
    if field_type is str and json_schema_extra.get("format") in (
        "file-path",
        "uri",
        "url",
    ):
        return gr.File(
            label=label,
            **kwargs,
        )

    # Handle HTML content
    if field_type is str and json_schema_extra.get("format") == "html":
        return gr.HTML(
            value=default,
            label=label,
            **kwargs,
        )

    # Handle markdown content
    if field_type is str and json_schema_extra.get("format") == "markdown":
        return gr.Markdown(
            value=default,
            label=label,
            **kwargs,
        )

    # Handle enums - use Dropdown for long enums, Radio for short ones
    if isinstance(field_type, type) and issubclass(field_type, Enum):
        choices = [e.value for e in field_type]
        if len(choices) > 5:  # Use Dropdown for longer lists
            return gr.Dropdown(
                choices=choices,
                label=label,
                value=default,
                info=field_info.description,
                **kwargs,
            )
        return gr.Radio(
            choices=choices,
            label=label,
            value=default,
            info=field_info.description,
            **kwargs,
        )

    # Handle number types with constraints
    if field_type in (int, float):
        # Extract constraints from metadata
        constraints = [
            m
            for m in field_info.metadata
            if hasattr(m, "gt")
            or hasattr(m, "ge")
            or hasattr(m, "lt")
            or hasattr(m, "le")
        ]
        min_val = next(
            (
                (c.gt if hasattr(c, "gt") else c.ge)
                for c in constraints
                if hasattr(c, "gt") or hasattr(c, "ge")
            ),
            None,
        )
        max_val = next(
            (
                (c.lt if hasattr(c, "lt") else c.le)
                for c in constraints
                if hasattr(c, "lt") or hasattr(c, "le")
            ),
            None,
        )
        multiple_of = next(
            (c.multiple_of for c in field_info.metadata if hasattr(c, "multiple_of")),
            1 if field_type is int else 0.1,
        )

        if min_val is not None and max_val is not None:
            return gr.Slider(
                minimum=min_val,
                maximum=max_val,
                step=multiple_of,
                label=label,
                value=field_info.default
                if field_info.default_factory is None
                else None,
                info=field_info.description,
                **kwargs,
            )

        return gr.Number(
            label=label,
            value=default,
            info=field_info.description,
            minimum=min_val,
            maximum=max_val,
            precision=next(
                (
                    c.decimal_places
                    for c in field_info.metadata
                    if hasattr(c, "decimal_places")
                ),
                None,
            ),
            **kwargs,
        )

    # Handle ByteSize
    if field_type is ByteSize:
        return gr.Textbox(
            label=label,
            info=field_info.description,
            placeholder="e.g., 1GB, 500MB, 1024B",
            **kwargs,
        )

    # Handle Decimal with precision
    if field_type is Decimal:
        return gr.Number(
            label=label,
            precision=getattr(field_info, "decimal_places", None),
            info=field_info.description,
            **kwargs,
        )

    # Handle boolean types
    if field_type is bool:
        return gr.Checkbox(
            label=label,
            value=default,
            info=field_info.description,
            **kwargs,
        )

    # Handle color inputs
    if field_type is str and json_schema_extra.get("format") == "color":
        return gr.ColorPicker(
            label=label,
            value=default,
            info=field_info.description,
            **kwargs,
        )

    # Handle date/time inputs
    if field_type is datetime or (
        field_type is str and json_schema_extra.get("format") in ("date", "date-time")
    ):
        return gr.DateTime(
            label=label,
            value=default,
            info=field_info.description,
            **kwargs,
        )

    # Handle Path types
    if field_type in (Path, PathType) or (
        get_origin(field_type) is Union
        and any(arg in (Path, PathType) for arg in get_args(field_type))
    ):
        # Check for directory path type
        is_directory = get_origin(field_type) is Annotated and any(
            isinstance(arg, PathType) and arg.path_type == "dir"
            for arg in get_args(field_type)[1:]
        )
        if is_directory:
            return gr.File(
                label=label,
                file_count="directory",
                **kwargs,
            )

        # Handle specific file types from json schema
        file_types = []
        if "format" in json_schema_extra:
            format_type = json_schema_extra["format"]
            if format_type == "image":
                file_types = ["jpg", "jpeg", "png", "gif"]
            elif format_type == "video":
                file_types = ["mp4", "avi", "mov"]
            elif format_type == "audio":
                file_types = ["mp3", "wav", "ogg"]
            elif format_type == "pdf":
                file_types = ["pdf"]

        # Check if it's a collection of file paths
        file_count = "single"
        if get_origin(field_type) in (list, tuple, set):
            inner_type = get_args(field_type)[0]
            if inner_type in (Path, PathType) or (
                get_origin(inner_type) is Union
                and any(arg in (Path, PathType) for arg in get_args(inner_type))
            ):
                file_count = "multiple"

        # Handle file paths
        return gr.File(
            label=label,
            file_types=file_types if file_types else None,
            file_count=file_count,
            **kwargs,
        )

    # Handle file paths
    if field_type is str and json_schema_extra.get("format") == "file-path":
        return gr.File(
            label=label,
            **kwargs,
        )

    # Fallback to textbox

    # Check various indicators that this field expects long-form text input
    min_length = next(
        (c.min_length for c in field_info.metadata if hasattr(c, "min_length")), 0
    )
    max_length = next(
        (c.max_length for c in field_info.metadata if hasattr(c, "max_length")), 0
    )

    is_long_text = any(
        [
            max_length > 128,  # Large max length
            min_length > 64,  # Non-trivial min length
            isinstance(field_info.default, str)
            and (  # Default is long or multiline
                len(field_info.default) > 128 or "\n" in field_info.default
            ),
            field_info.description
            and len(field_info.description) > 256,  # Description suggests long input
        ]
    )
    if is_long_text:
        return gr.TextArea(
            label=label,
            value=default,
            max_lines=10,
            info=field_info.description,
            **kwargs,
        )
    else:
        return gr.Textbox(
            label=label,
            lines=1,
            value=default,
            info=field_info.description,
            max_lines=1,
            **kwargs,
        )


def create_gradio_interface(function: Function, **kwargs: Any) -> "gr.Interface":
    import gradio as gr

    # Create input components
    inputs = []
    input_names = []
    for name, field in function.input.model_fields.items():
        comp = create_gradio_component(name, field)
        inputs.append(comp)
        input_names.append(name)

    # Create output components
    output_components = []
    output_names = []

    if issubclass(function.output, BaseModel):
        if (
            hasattr(function.output, "model_fields")
            and "root" in function.output.model_fields
        ):
            # Handle RootModel case
            comp = gr.Textbox(label="Output")
            output_components.append(comp)
            output_names.append("result")
        else:
            # Output is a regular Pydantic model with multiple fields
            for name, field in function.output.model_fields.items():
                comp = create_gradio_component(name, field)
                output_components.append(comp)
                output_names.append(name)
    else:
        # Fallback for simple types
        comp = gr.Textbox(label="Output")
        output_components.append(comp)
        output_names.append("result")

    # Add JSON output component with improved styling
    output_components.append(
        gr.JSON(
            label="JSON Output",
        )
    )
    output_names.append("json_output")

    # Add error output component with improved styling
    output_components.append(
        gr.Markdown(
            label="Errors",
            visible=False,
            value="",
        )
    )
    output_names.append("error")

    def gradio_fn(*args) -> list[Any]:
        try:
            input_data = dict(zip(input_names, args, strict=False))
            result = function(**input_data)

            outputs = []

            if isinstance(result, BaseModel):
                result_dict = result.model_dump()
                for name in output_names[:-2]:  # Exclude 'json_output' and 'error'
                    outputs.append(result_dict.get(name))
                outputs.append(result_dict)  # JSON representation
            else:
                outputs.append(result)  # Simple output value
                outputs.append(result)  # JSON representation

            # No error, so append None and set visible=False
            outputs.append(gr.update(value="", visible=False))

            return outputs

        except ValidationError as e:
            # Enhanced error formatting with Markdown
            error_messages = ["### Validation Errors\n"]
            for error in e.errors():
                loc = " → ".join(str(x) for x in error["loc"])
                error_messages.append(f"- **{loc}**: {error['msg']}")

            error_md = "\n".join(error_messages)

            # Return empty values for outputs and the error message
            return [None] * (len(output_components) - 1) + [
                gr.update(value=error_md, visible=True)
            ]

        except Exception as e:
            # Enhanced error formatting for general exceptions
            error_md = f"### Error\n\n**{e.__class__.__name__}**: {str(e)}"

            # Return empty values for outputs and the error message
            return [None] * (len(output_components) - 1) + [
                gr.update(value=error_md, visible=True)
            ]

    # Create interface with enhanced configuration
    interface_kwargs = {
        "fn": gradio_fn,
        "inputs": inputs,
        "outputs": output_components,
        "title": function.name,
        "description": function.description,
        "flagging_mode": "never",
        "theme": gr.themes.Soft(),
        "css": """
            .error { color: crimson; }
            .output-markdown { margin-top: 1rem; }
        """,
    }

    # Add any additional kwargs passed to the function
    interface_kwargs.update(kwargs)

    return gr.Interface(**interface_kwargs)

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

from hype.function import Function

if TYPE_CHECKING:
    import gradio as gr


def create_gradio_component(name: str, field_info: FieldInfo) -> "gr.Component":
    import gradio as gr

    field_type = field_info.annotation
    field_title = field_info.alias or name
    json_schema_extra = getattr(field_info, "json_schema_extra", {}) or {}

    # Handle Optional types
    if get_origin(field_type) is Union:
        args = get_args(field_type)
        if len(args) == 2 and type(None) in args:
            field_type = next(arg for arg in args if arg is not type(None))

    # Handle IP addresses
    if field_type in (
        IPvAnyAddress,
        IPvAnyInterface,
        IPvAnyNetwork,
    ):
        return gr.Textbox(
            label=field_title,
            info=field_info.description,
            placeholder=f"Enter valid {field_type.__name__}",
        )

    # Handle lists/sequences
    if get_origin(field_type) in (list, tuple, set):
        inner_type = get_args(field_type)[0]
        if inner_type in (str, int, float):
            return gr.Dropdown(
                multiselect=True,
                label=field_title,
                info=field_info.description,
                allow_custom_value=True,
                value=field_info.default
                if field_info.default_factory is None
                else None,
            )

    # Handle dictionaries
    if get_origin(field_type) is dict:
        return gr.JSON(
            label=field_title,
        )

    # Handle datetime types
    if field_type is datetime:
        return gr.DateTime(
            label=field_title,
            value=field_info.default if field_info.default_factory is None else None,
            info=field_info.description,
        )

    # Handle file paths and URLs
    if field_type is str and json_schema_extra.get("format") in (
        "file-path",
        "uri",
        "url",
    ):
        return gr.File(
            label=field_title,
        )

    # Handle HTML content
    if field_type is str and json_schema_extra.get("format") == "html":
        return gr.HTML(
            value=field_info.default if field_info.default_factory is None else None,
            label=field_title,
        )

    # Handle markdown content
    if field_type is str and json_schema_extra.get("format") == "markdown":
        return gr.Markdown(
            value=field_info.default if field_info.default_factory is None else None,
            label=field_title,
        )

    # Handle enums - use Dropdown for long enums, Radio for short ones
    if isinstance(field_type, type) and issubclass(field_type, Enum):
        choices = [e.value for e in field_type]
        if len(choices) > 5:  # Use Dropdown for longer lists
            return gr.Dropdown(
                choices=choices,
                label=field_title,
                value=field_info.default.value if field_info.default else None,
                info=field_info.description,
            )
        return gr.Radio(
            choices=choices,
            label=field_title,
            value=field_info.default.value if field_info.default else None,
            info=field_info.description,
        )

    # Handle number types with constraints
    if field_type in (int, float):
        # Use Slider if we have both min and max constraints
        has_min = getattr(field_info, "ge", getattr(field_info, "gt", None)) is not None
        has_max = getattr(field_info, "le", getattr(field_info, "lt", None)) is not None

        if has_min and has_max:
            return gr.Slider(
                minimum=getattr(field_info, "ge", getattr(field_info, "gt", None)),
                maximum=getattr(field_info, "le", getattr(field_info, "lt", None)),
                step=getattr(
                    field_info, "multiple_of", 1 if field_type is int else 0.1
                ),
                label=field_title,
                value=field_info.default
                if field_info.default_factory is None
                else None,
                info=field_info.description,
            )

        return gr.Number(
            label=field_title,
            value=field_info.default if field_info.default_factory is None else None,
            info=field_info.description,
            minimum=getattr(field_info, "ge", getattr(field_info, "gt", None)),
            maximum=getattr(field_info, "le", getattr(field_info, "lt", None)),
            precision=getattr(field_info, "decimal_places", None),
        )

    # Handle ByteSize
    if field_type is ByteSize:
        return gr.Textbox(
            label=field_title,
            info=field_info.description,
            placeholder="e.g., 1GB, 500MB, 1024B",
        )

    # Handle Decimal with precision
    if field_type is Decimal:
        return gr.Number(
            label=field_title,
            precision=getattr(field_info, "decimal_places", None),
            info=field_info.description,
        )

    # Handle boolean types
    if field_type is bool:
        return gr.Checkbox(
            label=field_title,
            value=field_info.default if field_info.default_factory is None else None,
            info=field_info.description,
        )

    # Handle color inputs
    if field_type is str and json_schema_extra.get("format") == "color":
        return gr.ColorPicker(
            label=field_title,
            value=field_info.default if field_info.default_factory is None else None,
            info=field_info.description,
        )

    # Handle date/time inputs
    if field_type is datetime or (
        field_type is str and json_schema_extra.get("format") in ("date", "date-time")
    ):
        return gr.DateTime(
            label=field_title,
            value=field_info.default if field_info.default_factory is None else None,
            info=field_info.description,
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
                label=field_title,
                file_count="directory",
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
            label=field_title,
            file_types=file_types if file_types else None,
            file_count=file_count,
        )

    # Handle file paths
    if field_type is str and json_schema_extra.get("format") == "file-path":
        return gr.File(
            label=field_title,
        )

    if field_type is str:
        # Check for long text
        is_long_text = (
            getattr(field_info, "max_length", 0) > 100
            or getattr(field_info, "description", "").count("\n") > 0
        )

        if is_long_text:
            return gr.TextArea(
                label=field_title,
                value=field_info.default
                if field_info.default_factory is None
                else None,
                max_lines=10,
                info=field_info.description,
            )
        else:
            return gr.Textbox(
                label=field_title,
                value=field_info.default
                if field_info.default_factory is None
                else None,
                lines=1,
                info=field_info.description,
                max_lines=1,
            )

    # Fallback to textbox
    return gr.Textbox(
        label=field_title,
        value=field_info.default if field_info.default_factory is None else None,
        lines=3 if getattr(field_info, "max_length", 0) > 100 else 1,
        info=field_info.description,
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

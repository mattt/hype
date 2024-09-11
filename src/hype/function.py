import inspect
from collections.abc import Callable, Mapping
from typing import (
    Annotated,
    Any,
    Generic,
    ParamSpec,
    TypeVar,
    get_args,
    get_origin,
    get_type_hints,
)

from docstring_parser import Docstring
from docstring_parser import parse as parse_docstring
from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    RootModel,
    create_model,
    validate_call,
)
from pydantic.fields import FieldInfo
from pydantic.json_schema import models_json_schema

Input = ParamSpec("Input")
Output = TypeVar("Output")


class Function(BaseModel, Generic[Input, Output]):
    _wrapped: Callable[Input, Output] = PrivateAttr(
        default_factory=lambda: lambda *args, **kwargs: None
    )
    name: str
    description: str | None
    input: type[BaseModel]
    output: type[BaseModel]

    @classmethod
    def from_function(cls, func: Callable[Input, Output]) -> "Function[Input, Output]":
        name = func.__name__

        docstring = parse_docstring(func.__doc__ or "")
        description = docstring.description

        input, output = input_and_output_types(func, docstring)

        function = cls(
            name=name,
            description=description,
            input=input,
            output=output,
        )
        function._wrapped = func
        return function

    def __call__(self, *args: Input.args, **kwargs: Input.kwargs) -> Output:  # pylint: disable=no-member
        return validate_call(validate_return=True)(self._wrapped)(*args, **kwargs)

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.input.model_json_schema()

    @property
    def output_schema(self) -> dict[str, Any]:
        return self.output.model_json_schema()

    @property
    def json_schema(self, title: str | None = None):
        _, top_level_schema = models_json_schema(
            [(self.input, "validation"), (self.output, "validation")],
            title=title or self.name,
        )
        return top_level_schema


def input_and_output_types(
    func: Callable,
    docstring: Docstring,
) -> tuple[type[BaseModel], type[BaseModel]]:
    signature = inspect.signature(func)
    input_types = get_type_hints(func)
    output_type = input_types.pop("return", None)

    input_field_definitions: Mapping[str, Any] = {}
    for order, (name, parameter) in enumerate(signature.parameters.items()):
        default: FieldInfo = (
            Field(...)
            if parameter.default is parameter.empty
            else (
                parameter.default
                if isinstance(parameter.default, FieldInfo)
                else Field(parameter.default)
            )
        )

        # Add field order
        default.json_schema_extra = {"x-order": order}

        # Add description from docstring if available
        if not default.description:
            if param_doc := next(
                (p for p in docstring.params if p.arg_name == name), None
            ):
                default.description = param_doc.description

        input_field_definitions[name] = (parameter.annotation, default)
    input = create_model("Input", **input_field_definitions, __module__=func.__module__)

    if (
        output_type
        and isinstance(output_type, type)
        and issubclass(output_type, BaseModel)
    ):
        output = output_type
    else:
        T = TypeVar("T")
        description = None

        # Check if return type is Annotated
        if get_origin(signature.return_annotation) is Annotated:
            base_type, *annotations = get_args(signature.return_annotation)
            for annotation in annotations:
                if isinstance(annotation, FieldInfo):
                    description = annotation.description
                    break
            T = TypeVar("T", bound=base_type)  # type: ignore
        else:
            T = TypeVar("T", bound=output_type)  # type: ignore
            if docstring.returns:
                description = docstring.returns.description

        class Output(RootModel[T]):  # pylint: disable=redefined-outer-name
            root: T = Field(  # type: ignore
                ..., description=description
            )

        output = Output

    return input, output


def export(func: Callable[Input, Output]) -> Function[Input, Output]:
    return Function.from_function(func)

import re
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any, cast

from hype.function import Function
from hype.tools import Result, Tools

if TYPE_CHECKING:
    from anthropic.types import ToolParam, ToolResultBlockParam, ToolUseBlock


ANTHROPIC_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class AnthropicTools(Tools[Result], Iterable["ToolParam"]):
    """
    Tools that can be used with Anthropic assistants.
    """

    def __init__(
        self, functions: Iterable[Function], result_type: type[Result] | None = None
    ) -> None:
        for function in functions:
            if not ANTHROPIC_TOOL_NAME_RE.match(function.name):
                raise ValueError(
                    f"Invalid function name: {function.name}, must match {ANTHROPIC_TOOL_NAME_RE.pattern}"
                )

        super().__init__(functions, result_type)

    def __iter__(self) -> Iterator["ToolParam"]:
        for function in self._tools.values():
            yield {
                "name": function.name,
                "description": function.description or "",
                "input_schema": function.input.model_json_schema(mode="validation"),
            }

    def __call__(self, tool_use: "ToolUseBlock") -> "ToolResultBlockParam":
        try:
            if not (function := self._tools.get(tool_use.name)):
                raise ValueError(f"Function {tool_use.name} not found")

            input = cast(dict[str, Any], tool_use.input)
            result = function(**input)

            return {
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": str(result),  # TODO: handle image output
                "is_error": False,
            }
        except Exception as exc:  # pylint: disable=broad-except
            self.future.set_exception(exc)

            return {
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": "An error occurred while calling the tool",
                "is_error": True,
            }


def create_anthropic_tools[Result](  # pylint: disable=redefined-outer-name
    functions: Function | Iterable[Function] | None = None,
    result_type: type[Result] | None = None,
) -> AnthropicTools[Result]:
    """
    Create tools that can be used with Anthropic assistants.

    :param functions: The functions to use.
    :param result_type: The type of the result to capture.
    """

    if functions is None:
        functions = []
    elif isinstance(functions, Function):
        functions = [functions]

    return AnthropicTools[Result](
        functions=functions,
        result_type=result_type,
    )

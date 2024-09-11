from collections.abc import Iterable, Iterator, Sequence
from typing import TYPE_CHECKING, Any, Union, cast

from hype.tools import Function, Result, Tools

if TYPE_CHECKING:
    from ollama._types import Tool, ToolCall


class OllamaTools(Tools[Result], list, Sequence["Tool"]):
    """
    Tools that can be used with Ollama assistants.
    """

    def __iter__(self) -> Iterator["Tool"]:
        for function in self._tools.values():
            parameters = function.input.model_json_schema(mode="validation")
            yield {
                "type": "function",
                "function": {
                    "name": function.name,
                    "description": function.description or "",
                    "parameters": cast(Any, parameters),
                },
            }

    def __len__(self) -> int:
        return len(self._tools)

    def __getitem__(self, key: int | str) -> Union["Tool", Function]:
        if isinstance(key, int):
            return list(self)[key]
        return self._tools[key]

    def __call__(self, tool_calls: list["ToolCall"]) -> list[Result]:
        outputs = []
        for tool_call in tool_calls:
            if not (function := self._tools.get(tool_call["function"]["name"])):
                raise ValueError(f"Function {tool_call['function']['name']} not found")

            input = tool_call["function"].get("arguments", {})
            result = function(**input)
            outputs.append(result)

        return outputs


def create_ollama_tools[Result](  # pylint: disable=redefined-outer-name
    functions: Function | Iterable[Function] | None = None,
    result_type: type[Result] | None = None,
) -> OllamaTools[Result]:
    """
    Create tools that can be used with Ollama models.

    :param functions: The functions to use.
    :param result_type: The type of the result to capture.
    """

    if functions is None:
        functions = []
    elif isinstance(functions, Function):
        functions = [functions]

    return OllamaTools[Result](
        functions=functions,
        result_type=result_type,
    )

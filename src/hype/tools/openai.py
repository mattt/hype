import json
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, TypeVar

from hype.tools import Function, Result, Tools

if TYPE_CHECKING:
    from openai.types.beta.threads.required_action_function_tool_call import (
        RequiredActionFunctionToolCall,
    )
    from openai.types.beta.threads.run_submit_tool_outputs_params import ToolOutput
    from openai.types.chat import ChatCompletionToolParam


class OpenAITools(Tools[Result], Iterable["ChatCompletionToolParam"]):
    """
    Tools that can be used with OpenAI assistants.
    """

    strict: bool = True

    def __iter__(self) -> Iterator["ChatCompletionToolParam"]:
        for function in self._tools.values():
            parameters = function.input.model_json_schema(mode="validation")
            parameters["additionalProperties"] = False

            parameters = _process_parameters(parameters)

            yield {
                "type": "function",
                "function": {
                    "name": function.name,
                    "strict": self.strict,
                    "parameters": parameters,
                },
            }

    def __call__(
        self, tool_calls: list["RequiredActionFunctionToolCall"]
    ) -> list["ToolOutput"]:
        outputs = []
        for tool_call in tool_calls:
            if not (function := self._tools.get(tool_call.function.name)):
                raise ValueError(f"Function {tool_call.function.name} not found")

            input = json.loads(tool_call.function.arguments)
            result = function(**input)
            outputs.append(
                {
                    "tool_call_id": tool_call.id,
                    "output": str(result),
                }
            )

        return outputs


def create_openai_tools[Result](  # pylint: disable=redefined-outer-name
    functions: Function | Iterable[Function] | None = None,
    result_type: type[Result] | None = None,
) -> OpenAITools[Result]:
    """
    Create tools that can be used with OpenAI assistants.

    :param functions: The functions to use.
    :param result_type: The type of the result to capture.
    """

    if functions is None:
        functions = []
    elif isinstance(functions, Function):
        functions = [functions]

    return OpenAITools[Result](
        functions=functions,
        result_type=result_type,
    )


T = TypeVar("T")


def _process_parameters(
    input: T,
) -> T:
    if isinstance(input, dict):
        return {
            k: _process_parameters(v)
            for k, v in input.items()
            if k not in ["title", "x-order"]
        }  # type: ignore
    elif isinstance(input, list):
        return [_process_parameters(i) for i in input]  # type: ignore
    else:
        return input

import json
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

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

    def __iter__(self) -> Iterator["ChatCompletionToolParam"]:
        for function in self._tools.values():
            parameters = function.input.model_json_schema(mode="validation")
            parameters["additionalProperties"] = False

            yield {
                "type": "function",
                "function": {
                    "name": function.name,
                    "strict": True,
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

import warnings
from abc import ABC, abstractmethod
from collections.abc import Container, Iterable, Iterator
from concurrent.futures import Future
from typing import Any, Generic, TypeVar

from hype.function import Function, export


def create_capture_function(dtype: type) -> tuple[Function, Future]:
    """
    Create a function that can capture structured output from an assistant.

    :param dtype: The type of the value to capture.
    """

    future = Future()

    @export
    def capture(value: dtype) -> None:
        """
        Returns structured output back to the user.
        Use this to end your response,
        but don't mention the existence of this function.

        :param value: The value to return to the user.
        """

        nonlocal future
        future.set_result(value)

    return capture, future


Result = TypeVar("Result")


class Tools(ABC, Generic[Result]):
    """
    A collection of functions that can be used by an assistant.

    This is an abstract base class.
    You should use one of the concrete subclasses, such as
    :class:`AnthropicTools` or :class:`OpenAIAssistantTools`.
    """

    future: Future
    """
    A future that will be set when the assistant provides a result
    or an exception is raised by a tool.
    """

    _tools: dict[str, Function]
    _result_type: type[Result] | None

    def __init__(
        self, functions: Iterable[Function], result_type: type[Result] | None
    ) -> None:
        self._tools = dict[str, Function]()
        for function in functions:
            if not function.description:
                warnings.warn(
                    message=f"Function {function.name} has no description",
                    category=RuntimeWarning,
                    stacklevel=1,
                )
            if function.name == "__return__":
                raise ValueError("Function name __return__ is reserved")
            if function.name in self._tools:
                raise ValueError(f"Duplicate function name: {function.name}")
            self._tools[function.name] = function

        if result_type is not None:
            self._result_type = result_type
            capture, future = create_capture_function(result_type)
            capture.name = "__return__"
            self._tools["__return__"] = capture
            self.future = future

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tools):
            return NotImplemented
        return self._tools == other._tools

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(functions={list(self._tools.keys())}, result_type={self._result_type.__name__ if self._result_type else 'None'})"

    def __str__(self) -> str:
        if self._result_type is None:
            return f"{self.__class__.__name__} with {len(self._tools)} functions"
        return f"{self.__class__.__name__} with {len(self._tools)-1} functions, returning {self._result_type.__name__}"

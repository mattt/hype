import ast
import operator
import re
from collections.abc import Callable
from typing import TypeVar

import anthropic
import pytest

import hype

Number = TypeVar("Number", int, float)


@hype.up
def calculate(expression: str) -> Number:
    """
    A simple calculator that performs basic arithmetic operations.

    :param expression: The mathematical expression to evaluate (e.g., '2 + 3 * 4').
    """

    operators: dict[type, Callable] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
    }

    def evaluate(node: ast.AST) -> Number:
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.UnaryOp):
            return operators[type(node.op)](evaluate(node.operand))
        elif isinstance(node, ast.BinOp):
            return operators[type(node.op)](evaluate(node.left), evaluate(node.right))
        else:
            raise ValueError(f"Unsupported operation: {node}")

    expression = re.sub(r"[^0-9+\-*/().]", "", expression)
    tree = ast.parse(expression, mode="eval")
    return evaluate(tree.body)


@hype.up
def is_prime(n: int) -> bool:
    """
    Check if a number is prime.

    :param n: The number to check.
    """
    if n <= 1:
        return False
    return all(n % i != 0 for i in range(2, int(n**0.5) + 1))


@pytest.mark.skip(reason="TODO")
def test_chat_with_claude():
    MODEL_NAME = "claude-3-5-sonnet-20240620"

    print("Starting test_chat_with_claude", flush=True)

    client = anthropic.Anthropic()
    user_message = "Is the sum of 19 and 23 prime?"
    tools = hype.create_anthropic_tools([calculate, is_prime], result_type=bool)

    messages: list[anthropic.types.MessageParam] = [
        {"role": "user", "content": user_message}
    ]

    while not tools.future:
        message = client.messages.create(
            model=MODEL_NAME,
            max_tokens=4096,
            messages=messages,
            tools=tools,
        )

        print(f"Response: {message.content}", flush=True)

        if message.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": message.content})

            tool_uses = [block for block in message.content if block.type == "tool_use"]

            for tool_use in tool_uses:
                tool_result = tools(tool_use)
                messages.append({"role": "user", "content": [tool_result]})

        else:
            response = message
            break

    assert tools.future == [True]

    assert not response.content

"""
This example shows how to use tools with Anthropic models.

`uv run examples/tool_use.py`
"""

# /// script
# dependencies = [
#   "anthropic",
#   "hype @ git+https://github.com/mattt/hype.git",
# ]
# ///

import ast
import operator
import re
from collections.abc import Callable
from typing import TypeVar

import anthropic

from hype.function import export
from hype.tools.anthropic import create_anthropic_tools

Number = TypeVar("Number", int, float)


@export
def calculate(expression: str) -> Number:
    """
    A simple calculator that performs basic arithmetic operations.
    Supports addition, subtraction, multiplication, division, and exponentiation.
    Use Python syntax for expressions.

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


@export
def prime_factors(n: int) -> list[int]:
    """
    Calculate the prime factors of a given number efficiently.

    :param n: The number to factorize.
    :return: A list of prime factors.
    """
    factors = set()

    # Handle 2 and 3 separately
    for p in (2, 3):
        while n % p == 0:
            factors.add(p)
            n //= p

    # Use wheel factorization for remaining factors
    # fmt: off
    wheel = (
        2, 4, 2, 4, 6, 2, 6, 4, 2, 4, 6, 6, 2, 6, 4, 2, 6, 4, 6, 8, 4, 2, 4, 2, 4, 8, # fmt: skip
    )
    # fmt: on
    w, d = 0, 5

    while d * d <= n:
        if n % d == 0:
            factors.add(d)
            n //= d
        else:
            d += wheel[w]
            w = (w + 1) % len(wheel)

    if n > 1:
        factors.add(n)

    return sorted(factors)


if __name__ == "__main__":
    client = anthropic.Anthropic()
    tools = create_anthropic_tools([calculate, prime_factors], result_type=bool)

    messages: list[anthropic.types.MessageParam] = [
        {
            "role": "user",
            "content": "Is two to the power of fifty-seven minus one prime?",
        }
    ]

    for message in messages:
        print(message["content"])

    while not tools.future.done():
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=2046,
            messages=messages,
            tools=tools,
        )

        for block in response.content:
            print(block)

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            for block in response.content:
                if block.type == "tool_use":
                    result = tools(block)
                    print("Result:", result, type(result))

                    messages.append(
                        {
                            "role": "user",
                            "content": [result],
                        }
                    )
        else:
            break

    print(f"Final result: {tools.future.result()}")

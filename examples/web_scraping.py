#!/usr/bin/env -S uv run --script

"""
This example shows how to use tools with Anthropic models.

Download `uv` to run this example: https://github.com/astral-sh/uv

```
export ANTHROPIC_API_KEY="..."

uv run examples/tool_use.py
```
"""

# /// script
# dependencies = [
#   "anthropic",
#   "hype @ git+https://github.com/mattt/hype.git",
#   "duckduckgo-search",
#   "beautifulsoup4",
#   "pydantic",
#   "httpx",
#   "pint",
# ]
# ///

import datetime
from textwrap import dedent
from typing import Literal

import anthropic
import httpx
import pint
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from pydantic import BaseModel

import hype

ureg = pint.UnitRegistry()


class Recipe(BaseModel):
    """
    A recipe with its name, prep time, cook time, ingredients, and steps.
    """

    name: str
    """The name of the recipe."""

    prep_time: datetime.timedelta
    """The time it takes to prepare the recipe."""

    cook_time: datetime.timedelta
    """The time it takes to cook the recipe."""

    ingredients: list[str]
    """The ingredients in the recipe."""

    steps: list[str]
    """A list of steps for preparing the recipe."""


@hype.up
def web_search(query: str, num_results: int = 5) -> list[dict]:
    """
    Perform a web search using DuckDuckGo.

    :param query: The search query.
    :param num_results: Number of results to return (default: 5).
    :return: A list of dictionaries containing search results.
    """
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=num_results))


@hype.up
def scrape_webpage(url: str) -> str:
    """
    Scrape the content of a webpage.

    :param url: The URL of the webpage to scrape.
    :return: The text content of the webpage.
    """
    with httpx.Client() as client:  # pylint: disable=redefined-outer-name
        response = client.get(url, timeout=30)  # pylint: disable=redefined-outer-name
        soup = BeautifulSoup(response.content, "html.parser")
        return soup.get_text(strip=True)


# fmt:off
Unit = Literal[
    "g", "kg", "mg", "µg",
    "l", "ml", "µl",
    "cup", "tsp", "tbsp",
    "floz", "pt", "qt", "gal",
    "oz", "lb",
    "°C", "°F"
]
# fmt:on


@hype.up
def convert_quantity(value: float, from_unit: Unit, to_unit: Unit) -> tuple[float, str]:
    """
    Convert quantity from one unit to another.

    :param value: The numeric value to convert.
    :param from_unit: The unit to convert from.
    :param to_unit: The unit to convert to.
    :return: A tuple with the converted value and unit.
    """
    quantity = value * ureg(from_unit)
    converted = quantity.to(to_unit)
    return converted.magnitude, str(converted.units)


if __name__ == "__main__":
    client = anthropic.Anthropic()
    tools = hype.create_anthropic_tools(
        [web_search, scrape_webpage, convert_quantity],
        result_type=Recipe,
    )

    messages: list[anthropic.types.MessageParam] = [
        {
            "role": "user",
            "content": dedent(
                """
                Find a recipe for avocado and black bean tacos,
                convert units to metric,
                and translate instructions into Italian.
                """.strip(),
            ),
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
                    print("Result:", result)

                    messages.append(
                        {
                            "role": "user",
                            "content": [result],
                        }
                    )
        else:
            break

    print(f"Final result: {tools.future.result()}")

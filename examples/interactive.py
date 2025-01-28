#!/usr/bin/env -S uv run --script

"""
This example shows how to create interactive tools.

Install `ollama` here: https://ollama.com
Download `uv` to run this example: https://github.com/astral-sh/uv

```
ollama pull llama3.2

uv run examples/interactive.py
```
"""

# /// script
# dependencies = [
#   "ollama",
#   "hype @ git+https://github.com/mattt/hype.git",
# ]
# ///

import ollama

import hype


@hype.up
def get_user_name() -> str:
    """
    Get the user's name.

    This method takes no arguments and returns the user's name.
    :return: The user's name.
    """

    return input("What is your name? ")


if __name__ == "__main__":
    tools = hype.create_ollama_tools(
        [
            get_user_name,
        ],
    )

    response = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "user",
                "content": "Ask the user their name and then greet them by name.",
            },
        ],
        tools=tools,
    )

    name, *_ = tools(response["message"]["tool_calls"])  # pylint: disable=unsubscriptable-object

    print()
    print(f"Hello, {name}!")
    print("Please wait while I generate a poem for you...")
    print()

    response = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "user",
                "content": f"""
                Write an acrostic poem about a person named "{name}".
                Return the poem as a string. Do not include any other text.
                DO NOT MISSPELL THE PERSON'S NAME.
                """,
            },
        ],
    )

    print(response["message"]["content"])

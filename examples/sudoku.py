#!/usr/bin/env -S uv run --script

"""
This example shows how to solve Sudoku puzzles with OpenAI.

Download `uv` to run this example: https://github.com/astral-sh/uv

```
export OPENAI_API_KEY="..."

uv run examples/sudoku.py
```
"""

# /// script
# dependencies = [
#   "openai",
#   "hype @ git+https://github.com/mattt/hype.git",
# ]
# ///

import copy
from collections.abc import Iterator
from itertools import chain
from typing import Annotated, Literal

from pydantic import Field, RootModel

import hype

DIGITS = set(range(1, 10))

Status = Literal["solved", "incomplete", "invalid"]
Digit = Annotated[int, Field(ge=1, le=9)]
Grid = Annotated[
    list[Annotated[list[Digit | None], Field(min_length=9, max_length=9)]],
    Field(min_length=9, max_length=9),
]
Position = tuple[int, int]


class Sudoku(RootModel):
    # root: Grid
    root: list[list[int | None]]

    @property
    def status(self) -> Status:
        for collection in chain(self.rows, self.columns, self.regions):
            digits = set()
            for cell in collection:
                if cell is None:
                    return "incomplete"
                digits.add(cell)
            if digits != DIGITS:
                return "invalid"
        return "solved"

    @classmethod
    def parse(cls, text: str) -> "Sudoku":
        rows = []
        for line in text.splitlines():
            columns = []
            for char in line:
                if char in {".", "_", "x", "X", "0"}:
                    columns.append(None)
                elif char.isdigit():
                    columns.append(int(char))
            if any(col is not None for col in columns):
                rows.append(columns)
        return cls(root=rows)

    @property
    def rows(self) -> Iterator[list[Digit | None]]:
        yield from self.root

    @property
    def columns(self) -> Iterator[list[Digit | None]]:
        yield from [[self[(i, j)] for i in range(9)] for j in range(9)]

    @property
    def regions(self) -> Iterator[list[Digit | None]]:
        yield from [
            [self[(r + i // 3, c + i % 3)] for i in range(9)]
            for r in range(0, 9, 3)
            for c in range(0, 9, 3)
        ]

    def __iter__(self) -> Iterator[tuple[Position, Digit | None]]:
        for i, row in enumerate(self.rows):
            for j, cell in enumerate(row):
                yield (i, j), cell

    def __getitem__(self, key: Position) -> Digit | None:
        return self.root[key[0]][key[1]]

    def __setitem__(self, key: Position, value: Digit | None) -> None:
        self.root[key[0]][key[1]] = value

    def __delitem__(self, key: Position) -> None:
        self.__setitem__(key, None)

    def __str__(self) -> str:
        result = []
        for i in range(9):
            if i in (3, 6):
                result.append("-" * 11)
            row = []
            for j in range(9):
                if j in (3, 6):
                    row.append("|")
                cell = self.root[i][j]
                row.append(str(cell) if cell is not None else " ")
            result.append("".join(row))
        return "\n".join(result)


def solutions(puzzle: Sudoku) -> Iterator[Sudoku]:
    match puzzle.status:
        case "solved":
            yield puzzle
            return
        case "incomplete":
            pass
        case "invalid":
            return

    rows = list(puzzle.rows)
    columns = list(puzzle.columns)
    regions = list(puzzle.regions)

    possibilities: dict[Position, set[Digit]] = {}
    for (row, col), val in puzzle:
        if val is None:
            possibilities[(row, col)] = (
                set(DIGITS)
                - set(
                    chain(
                        rows[row],
                        columns[col],
                        regions[3 * (row // 3) + (col // 3)],
                    )
                )
                - {None}
            )
    if not possibilities:
        return

    position, digits = min(
        possibilities.items(),
        key=lambda item: len(item[1]),
    )
    for digit in digits:
        candidate = copy.deepcopy(puzzle)
        candidate[position] = digit
        yield from solutions(candidate)


@hype.up
def solve(puzzle: Sudoku) -> Sudoku | None:
    """Solve a Sudoku puzzle."""
    try:
        return next(solutions(puzzle))
    except StopIteration:
        return None


if __name__ == "__main__":
    from openai import OpenAI

    client = OpenAI()

    tools = hype.create_openai_tools([solve])
    tools.strict = False

    print("Creating assistant...")
    assistant = client.beta.assistants.create(
        instructions="You are a helpful assistant that can solve Sudoku puzzles. Use the provided tools to solve puzzles.",
        model="gpt-4o-2024-08-06",
        tools=tools,
    )

    print("Creating thread...")
    thread = client.beta.threads.create()

    print("Sending message...")
    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=[
            {"type": "text", "text": "Solve the Sudoku puzzle."},
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Sudoku_Puzzle_by_L2G-20050714_standardized_layout.svg/500px-Sudoku_Puzzle_by_L2G-20050714_standardized_layout.svg.png",
                },
            },
        ],
    )

    print("Running assistant...")
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=assistant.id,
    )

    if run.required_action and run.required_action.submit_tool_outputs:
        tool_outputs = tools(run.required_action.submit_tool_outputs.tool_calls)

        if tool_outputs:
            run = client.beta.threads.runs.submit_tool_outputs_and_poll(
                thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs
            )
        else:
            print("No tool outputs to submit.")
    else:
        print("Run failed:", run.status)

    if run.status == "completed":
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        print(messages)
    else:
        print(run.status)

    # Clean up
    client.beta.assistants.delete(assistant.id)
    client.beta.threads.delete(thread.id)

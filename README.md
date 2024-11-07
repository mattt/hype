# Hype 🆙

> [!WARNING]  
> This project is in early active development.
> Expect frequent updates and potential breaking changes.

Hype gives your Python functions super powers.

```python hl_lines="5"
import hype
from pydantic import Field


@hype.up
def divide(
    x: int,
    y: int = Field(gt=0),
) -> int:
    """
    Divides one number by another.
    :param x: The numerator
    :param y: The denominator
    :return: The quotient
    """
    return x // y
```

Hyped up functions look great to humans 💅

```pycon
>>> divide
Function(name='divide', description='Divides one number by another.', input=(x: int, y: int), output=int)
```

They look great to robots, too 🤖❤️

```pycon
>>> divide.json_schema
"{'$defs': {'Input': { ... } } }"
```

You call them the same as you would any other function,
except now you get the benefit of automatic input validation 🦺

```pycon
>>> divide(4, 2)
2

>>> divide(y=0)
ValidationError: 2 validation errors for divide
x
  Missing required argument [type=missing_argument, input_value=ArgsKwargs((), {'y': 0}), input_type=ArgsKwargs]
    For further information visit https://errors.pydantic.dev/2.9/v/missing_argument
y
  Input should be greater than 0 [type=greater_than, input_value=0, input_type=int]
    For further information visit https://errors.pydantic.dev/2.9/v/greater_than
```

Hype gives Python functions a universal calling interface.

Run hyped up functions from the command-line ⚙️

```console
# Hyped up functions are

$ hype run example.py divide 9 3
3

# You can even run batch jobs
$ python -c "import json, random; print('\n'.join(json.dumps({'x': random.randint(1,1000), 'y': random.randint(0,100)}) for _ in range(3)))" > input.jsonl
$ cat input.jsonl
{"x": 49, "y": 7}
{"x": 438, "y": 73}
{"x": 1, "y": 0}

$ hype run example.py divide --input input.jsonl
7
6
Error: 1 validation error for divide
y
  Input should be greater than 0 [type=greater_than, input_value=0, input_type=int]
    For further information visit https://errors.pydantic.dev/2.9/v/greater_than
```

Or serve them through an HTTP interface 🕸️

```console
$ hype serve example.py &
Starting server at http://127.0.0.1:4973
Loading module...
✓ Found 1 function
✓ API server ready

$ curl http://localhost:4973/openapi.json | jq .components.schemas.divide_Input
{
  "type": "object",
  "properties": {
    "x": {
      "type": "integer",
      "title": "X",
      "description": "The numerator",
      "x-order": 0
    },
    "y": {
      "type": "integer",
      "exclusiveMinimum": 0.0,
      "title": "Y",
      "description": "The denominator",
      "x-order": 1
    }
  },
  "required": [
    "x",
    "y"
  ]
}

$ curl -i -X POST http://localhost:4973/divide \
          -H "Content-Type: application/json"  \
          -d '{"x": 99, "y": 3}'
HTTP/1.1 200 OK
Content-Length: 2
Content-Type: application/json

33
```

Hyped up functions have tool definitions that you can pass to LLMs like
[Claude](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) and
[ChatGPT](https://platform.openai.com/docs/guides/function-calling).

For example,
let's define a pair of functions to help answer a maths problem.

```python
import hype

@hype.up
def calculate(expression: str) -> int | float:
    """
    Performs basic arithmetic operations.
    Supports addition, subtraction, multiplication, and division, and exponentiation.

    :param expression: The mathematical expression to evaluate (e.g., '2 + 3 * 4').
                       This expression uses Python syntax.
    """
    ...

@hype.up
def prime_factors(n: int) -> set[int]:
    """
    Determines whether a number is prime.

    :param n: The number to check.
    """
    ...
```

Hyped up functions can be passed to `hype.create_anthropic_tools`
to make them available as tools to Claude.
You can set an optional `result_type` to shape the language model's output.

In this example, we pass the `calculate` and `prime_factors` functions
and set `result_type` to `bool` to indicate that we want a final
`True` or `False` answer.

```python
import anthropic

client = anthropic.Anthropic()
tools = hype.create_anthropic_tools([calculate, prime_factors], result_type=bool)

messages: list[anthropic.types.MessageParam] = [
    {
        "role": "user",
        "content": "Is two to the power of 57 minus one prime?",
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
                messages.append(
                    {
                        "role": "user",
                        "content": [tools(block)],
                    }
                )
    else:
        break

result = tools.future.result()
print(result, type(result)) # => False, bool
```

Here's a transcript of the exchange:

<dl>
  <dt>👤 Human</dt>
  <dd>Is two to the power of 88 minus one prime?</dd>

  <dt>🤖 AI</dt>
  <dd>
    <p>To answer this question, we need to perform a couple of steps:</p>
    <ol>
      <li>Calculate 2^57 - 1</li>
      <li>Check if the resulting number is prime</li>
    </ol>
    <p>Let's start with the calculation:</p>
    <code>[tool_use name="calculate" input={'expression': '2**57 - 1'}]</code>
  </dd>

  <dt>👤 Human</dt>
  <dd><code>[tool_use result=144115188075855871]</code></dd>

  <dt>🤖 AI</dt>
  <dd>
    <p>Now that we have the result of 2^57 - 1, which is 144115188075855871, we need to check if this number is prime.</p>
    <p>We can do this by finding its prime factors. If the number has only one prime factor (itself), then it is prime.</p>
    <p>Let's use the prime_factors function to check:</p>
    <code>[tool_use name="prime_factors" input={'n': 144115188075855871}]</code>
  </dd>

  <dt>👤 Human</dt>
  <dd><code>[tool_use result=[7, 32377, 635879915089]]</code></dd>

  <dt>🤖 AI</dt>
  <dd>
    <p>The prime_factors function returned [7, 32377, 635879915089], which means that 144115188075855871 (2^57 - 1) is not a prime number.</p>
    <code>[tool_use name="__return__" input={'result': False}]</code>
  </dd>
</dl>

> [!TIP]
> There are other Python libraries out there for working with chat assistants,
> but many wrap client libraries in ways that take control away from you.
>
> Hype is designed with composability in mind, and doesn't get in your way.

See [examples/tool_use.py](/examples/tool_use.py)
for the full, working example.

## Installation

```console
pip install git+https://github.com/mattt/hype.git
```

## Tool Use Examples

### Return typed outputs from AI assistants

Hype makes it easy to <dfn>shape</dfn> outputs from a chat assistant.

In the previous example, we showed how to use tools to answer a math question,
but language models can do a lot on their own.
Sometimes all you need is a way to get a particular kind of answer.

For instance, GPT-4o excels at extracting structured information
from natural language text,
like flight details from the body of an email.

First, define a `FlightDetails` class.
Really go to town with [Pydantic](https://docs.pydantic.dev/latest/).
The more precise and pedantic,
the better your results will be.

```python
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

AirportCode = Annotated[str, StringConstraints(min_length=3, max_length=3, pattern=r'^[A-Z]+$')]

class FlightDetails(BaseModel):
    origin: AirportCode = Field(
        description="Three-letter IATA airport code for the departure airport."
    )

    destination: AirportCode = Field(
        description="Three-letter IATA airport code for the arrival airport."
    )

    departure_time: datetime = Field(
        description="When the flight is scheduled to depart from its origin"
    )

    arrival_time: datetime = Field(
        description="When the flight is scheduled to arrive at its destination"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "origin": "LAX",
                    "destination": "JFK",
                    "departure_time": "2023-06-15T08:00:00Z",
                    "arrival_time": "2023-06-15T16:30:00Z"
                }
            ]
        }
    }
```

From there,
the process is much the same as what we did before.

```python
from anthropic import Anthropic
import hype

client = Anthropic()
tools = hype.create_anthropic_tools(result_type=FlightDetails)

messages: list[MessageParam] = [
    {
        "role": "user",
        "content": """
            Extract the flight details from following email:


            It's time to check in for your flight.
            Use the app for smooth sailing and we'll see you soon!
            Confirmation code: ABCDEF

            Your trip details
            Flight 420
            Seat  10D
            5:00 PM            6:30 PM
            SFO                PDX
            San Francisco      Portland, OR

            Departure          Arrival
            9/20/2023          9/20/2023
            """,
    }
]

response = client.messages.create(
    model="claude-3-5-sonnet-20240620",
    max_tokens=2046,
    messages=messages,
    tools=tools,
)

if response.stop_reason == "tool_use":
    for block in response.content:
        if block.type == "tool_use":
            result = tools(block)

result = tools.future.result()
print(result.model_dump_json(indent=2))
```

```json
{
  "origin": "SFO",
  "destination": "PDX",
  "departure_time": "2023-09-20T17:00:00Z",
  "arrival_time": "2023-09-20T18:30:00Z"
}
```

See [examples/output_shaping.py](/examples/output_shaping.py)
for the full, working example.

### Search the web and scrape webpages

Find recipes with DuckDuckGo,
scrape content from search results,
convert units to metric,
and return structured output.

See [examples/web_scaping.py](/examples/web_scraping.py).

### Perform retrival augmented generation (RAG) with vector store

Build up a database of documents in SQLite
using an extension for vector search,
and use that to answer questions.

See [examples/rag.py](/examples/rag.py).

### Extract structured information from images

Use GPT-4o to extract board state from a picture of a Sudoku puzzle
and use tools to solve it.

See [examples/sudoku.py](/examples/sudoku.py).

### Build interactive tools

Build tools that get input from the user interactively.

See [examples/interactive.py](/examples/interactive.py).

### Interact with macOS using AppleScript and Ollama

A glimmer of how to build your own self-hosted, local-first personal assistant.

See [examples/system_events.py](/examples/system_events.py).

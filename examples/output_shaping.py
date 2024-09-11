"""
This example shows how to use output shaping with Anthropic models.

`uv run examples/output_shaping.py`
"""

# /// script
# dependencies = [
#   "anthropic",
#   "hype @ git+https://github.com/mattt/hype.git",
# ]
# ///

from datetime import datetime
from typing import Annotated

from anthropic import Anthropic
from anthropic.types import MessageParam
from pydantic import BaseModel, Field, StringConstraints

from hype import create_anthropic_tools

AirportCode = Annotated[
    str, StringConstraints(min_length=3, max_length=3, pattern=r"^[A-Z]+$")
]


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
                    "arrival_time": "2023-06-15T16:30:00Z",
                }
            ]
        }
    }


if __name__ == "__main__":
    client = Anthropic()
    tools = create_anthropic_tools(result_type=FlightDetails)

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
    print(f"Final result: {result.model_dump_json(indent=2)}")

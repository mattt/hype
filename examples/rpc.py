#!/usr/bin/env -S uv run --script

"""
This example shows how to serve a function over HTTP with Hype.

Download `uv` to run this example: https://github.com/astral-sh/uv

```
uv run examples/rpc.py
```
"""

import json
import logging

from fastapi.testclient import TestClient

import hype


@hype.up
def add(x: int, y: int) -> int:
    return x + y


if __name__ == "__main__":
    logging.basicConfig(
        format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )

    app = hype.create_fastapi_app([add])

    with TestClient(app) as client:
        response = client.get("/openapi.json")
        print("OpenAPI schema:")
        print(json.dumps(response.json(), indent=2))

        print()

        response = client.post("/add", json={"x": 1, "y": 2})
        print(f"Response: {response.json()}")

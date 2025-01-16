import asyncio
import io
import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest

import hype
from hype.mcp import create_mcp_stdio_handler
from hype.mcp.jsonrpc import JsonRpcRequest, JsonRpcResponse


@pytest.fixture
def math_functions():
    """Create test math functions"""

    @hype.up
    def add(a: int, b: int) -> int:
        return a + b

    @hype.up
    def multiply(x: int, y: int) -> int:
        return x * y

    @hype.up
    async def divide(a: int, b: int) -> float:
        return a / b

    return [add, multiply, divide]


@pytest.fixture
def stdio_streams():
    """Create test input/output streams"""
    input_stream = io.StringIO()
    output_stream = io.StringIO()
    return input_stream, output_stream


def send_request(
    input_stream: io.StringIO, method: str, params: dict[str, Any], id: int = 1
) -> None:
    """Send a JSON-RPC request to the input stream."""
    request = JsonRpcRequest(jsonrpc="2.0", method=method, params=params, id=id)
    input_stream.write(request.model_dump_json() + "\n")
    input_stream.seek(0)


def get_response(output_stream: io.StringIO) -> dict[str, Any]:
    """Get JSON-RPC response from the output stream."""
    output = output_stream.getvalue().strip()
    if not output:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": "No response received"},
            "id": None,
        }
    return json.loads(output.split("\n")[0])  # Get first response if multiple


async def process_request_async(
    functions, input_stream, output_stream
) -> AsyncGenerator[JsonRpcResponse, None]:
    """Process requests through the stdio handler, yielding responses."""
    handler = create_mcp_stdio_handler(functions, input_stream, output_stream)
    async for response in handler:
        yield response


async def process_single_request(
    functions, input_stream, output_stream
) -> dict[str, Any]:
    """Process a single request and return its response as a dict."""
    try:
        async for response in process_request_async(
            functions, input_stream, output_stream
        ):
            return response.model_dump()
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": str(e)},
            "id": None,
        }


def process_request(functions, input_stream, output_stream) -> dict[str, Any]:
    """Synchronous wrapper to process a single request."""
    return asyncio.run(process_single_request(functions, input_stream, output_stream))


@pytest.mark.asyncio
async def test_stdio_list_functions_async(math_functions, stdio_streams):
    """Test listing functions via stdio transport"""
    input_stream, output_stream = stdio_streams

    # Send request
    send_request(input_stream, "tools/list", {})

    # Process and validate response
    async for response in process_request_async(
        math_functions, input_stream, output_stream
    ):
        response_dict = response.model_dump()
        assert response_dict["jsonrpc"] == "2.0"
        assert response_dict["id"] == 1
        assert "result" in response_dict

        functions = response_dict["result"]
        assert len(functions) == 3

        function_names = {f["name"] for f in functions}
        assert function_names == {"add", "multiply", "divide"}
        break  # We expect only one response


@pytest.mark.asyncio
async def test_stdio_async_function_async(math_functions, stdio_streams):
    """Test calling an async function"""
    input_stream, output_stream = stdio_streams

    # Send request to async divide function
    send_request(
        input_stream, "tools/call", {"name": "divide", "arguments": {"a": 10, "b": 2}}
    )

    # Process and validate response
    async for response in process_request_async(
        math_functions, input_stream, output_stream
    ):
        response_dict = response.model_dump()
        assert response_dict["jsonrpc"] == "2.0"
        assert response_dict["id"] == 1
        assert "result" in response_dict

        # The response should contain the actual result, not a coroutine
        result = response_dict["result"]["content"][0]["text"]
        assert float(result) == 5.0
        break  # We expect only one response


def test_stdio_tool_call(math_functions, stdio_streams):
    """Test calling a tool via stdio transport"""
    input_stream, output_stream = stdio_streams

    # Send request
    send_request(
        input_stream, "tools/call", {"name": "add", "arguments": {"a": 2, "b": 3}}
    )

    # Process and validate response
    response = process_request(math_functions, input_stream, output_stream)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "result" in response
    assert response["result"]["content"][0]["text"] == "5"


def test_stdio_method_not_found(math_functions, stdio_streams):
    """Test handling unknown method"""
    input_stream, output_stream = stdio_streams

    # Send request with unknown method
    send_request(input_stream, "unknown", {})

    # Process and validate response
    response = process_request(math_functions, input_stream, output_stream)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "error" in response
    assert response["error"]["code"] == -32601
    assert "Method not found: unknown" in response["error"]["message"]


def test_stdio_id_types(math_functions, stdio_streams):
    """Test different JSON-RPC ID types"""
    input_stream, output_stream = stdio_streams

    # Test string ID
    send_request(input_stream, "tools/list", {}, id="test-id")
    response = process_request(math_functions, input_stream, output_stream)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "test-id"
    assert "result" in response

    # Reset streams for next test
    input_stream = io.StringIO()
    output_stream = io.StringIO()

    # Test null ID
    send_request(input_stream, "tools/list", {}, id=None)
    response = process_request(math_functions, input_stream, output_stream)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] is None
    assert "result" in response


@pytest.mark.asyncio
async def test_stdio_error_data(math_functions, stdio_streams):
    """Test error data field in responses"""
    input_stream, output_stream = stdio_streams

    # Test error with data
    send_request(
        input_stream,
        "tools/call",
        {"name": "divide", "arguments": {"a": 1, "b": 0}},
        id=1,
    )
    response = await process_single_request(math_functions, input_stream, output_stream)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "error" in response
    assert response["error"]["code"] == -32603
    assert "division by zero" in str(response["error"]["message"]).lower()


def test_stdio_concurrent_requests(math_functions, stdio_streams):
    """Test handling multiple requests concurrently"""
    input_stream, output_stream = stdio_streams

    # Send multiple requests
    requests = [("add", {"a": i, "b": i}) for i in range(5)]

    # Send each request and process it immediately
    for i, (method, params) in enumerate(requests):
        # Reset stream position for each request
        input_stream.seek(0)
        input_stream.truncate()

        send_request(
            input_stream, "tools/call", {"name": method, "arguments": params}, id=i
        )

        response = process_request(math_functions, input_stream, output_stream)
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == i
        assert "result" in response
        result = int(response["result"]["content"][0]["text"])
        assert result == i * 2  # add(i, i) = i * 2


def test_stdio_non_utf8_input(math_functions, stdio_streams):
    """Test handling non-UTF8 input"""
    input_stream, output_stream = stdio_streams

    # Create a new BytesIO for binary operations
    binary_input = io.BytesIO(b"\xff\xfe\xfd\n")
    text_input = io.TextIOWrapper(binary_input, errors="strict")

    # Process request
    response = process_request(math_functions, text_input, output_stream)
    assert response["jsonrpc"] == "2.0"
    assert "error" in response
    assert response["error"]["code"] == -32700  # Parse error
    assert "'utf-8' codec can't decode byte" in str(response["error"]["message"])


def test_stdio_stream_errors(math_functions, stdio_streams):
    """Test handling stream errors"""
    input_stream, output_stream = stdio_streams

    try:
        # Test read error
        input_stream.close()
        response = process_request(math_functions, input_stream, output_stream)
        assert response["jsonrpc"] == "2.0"
        assert "error" in response
        assert response["error"]["code"] == -32603  # Internal error
    except ValueError:
        # Expected error for closed stream
        pass

    # Reset streams for write error test
    input_stream = io.StringIO()
    output_stream = io.StringIO()

    try:
        send_request(input_stream, "tools/list", {})
        output_stream.close()
        response = process_request(math_functions, input_stream, output_stream)
        assert response["jsonrpc"] == "2.0"
        assert "error" in response
        assert response["error"]["code"] == -32603  # Internal error
    except ValueError:
        # Expected error for closed stream
        pass

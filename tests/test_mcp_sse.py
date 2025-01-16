import json

import pytest
from fastapi.testclient import TestClient

import hype
from hype.mcp import create_mcp_sse_app


@pytest.fixture
def math_app():
    """Create a test app with simple math functions"""

    @hype.up
    def add(a: int, b: int) -> int:
        return a + b

    @hype.up
    def multiply(x: int, y: int) -> int:
        return x * y

    @hype.up
    async def divide(a: int, b: int) -> float:
        return a / b

    app = create_mcp_sse_app(
        functions=[add, multiply, divide],
        title="Test Math Service",
        description="Test MCP math service",
    )
    return app


def test_sse_headers(math_app):
    """Test SSE headers are set correctly"""
    with TestClient(math_app) as client:
        response = client.post(
            "/v1/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "create_message",
                "params": {
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": "test"}]}
                    ],
                },
                "id": 1,
            },
        )
        assert response.status_code == 200
        assert "MCP-Version" in response.headers
        assert response.headers["MCP-Version"] == "2024-11-05"
        assert "MCP-Latency" in response.headers


def test_sse_streaming_message(math_app):
    """Test streaming message creation"""
    with TestClient(math_app) as client:
        response = client.post(
            "/v1/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "add",
                    "arguments": {"a": 2, "b": 3},
                    "stream": True,
                },
                "id": 1,
            },
            headers={"Accept": "text/event-stream"},
        )
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("text/event-stream")
        assert response.headers.get("MCP-Stream") == "true"

        events = []
        current_event = None
        current_data = []

        # Read all events from response content
        for line in response.content.decode().split("\n"):
            if not line:
                # Empty line marks end of event
                if current_event and current_data:
                    events.append(
                        {"event": current_event, "data": "\n".join(current_data)}
                    )
                current_event = None
                current_data = []
                continue

            if line.startswith("event:"):
                current_event = line[6:].strip()
            elif line.startswith("data:"):
                current_data.append(line[5:].strip())

        # First event should be endpoint
        assert len(events) >= 2  # At least endpoint and one message
        assert events[0]["event"] == "endpoint"
        assert events[0]["data"].startswith("http")

        # Second event should be message
        assert events[1]["event"] == "message"
        message_data = json.loads(events[1]["data"])
        assert message_data["result"]["content"][0]["text"] == "5"


def test_sse_tool_call(math_app):
    """Test tool call with SSE transport"""
    with TestClient(math_app) as client:
        response = client.post(
            "/v1/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "add", "arguments": {"a": 2, "b": 3}},
                "id": 1,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert "result" in result
        assert result["result"]["content"][0]["text"] == "5"


def test_sse_method_not_found(math_app):
    """Test handling unknown method"""
    with TestClient(math_app) as client:
        response = client.post(
            "/v1/jsonrpc",
            json={"jsonrpc": "2.0", "method": "unknown", "params": {}, "id": 1},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert "error" in result
        assert result["error"]["code"] == -32601
        assert "Method not found: unknown" in result["error"]["message"]


def test_sse_invalid_params(math_app):
    """Test handling invalid parameters with SSE transport"""
    with TestClient(math_app) as client:
        response = client.post(
            "/v1/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "add", "arguments": {"a": "not_a_number", "b": 3}},
                "id": 1,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert "error" in result
        assert result["error"]["code"] == -32602  # Invalid params error code


def test_sse_async_function(math_app):
    """Test calling async function with SSE transport"""
    with TestClient(math_app) as client:
        response = client.post(
            "/v1/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "divide", "arguments": {"a": 10, "b": 2}},
                "id": 1,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert "result" in result
        assert result["result"]["content"][0]["text"] == "5.0"


def test_sse_division_by_zero(math_app):
    """Test handling runtime errors with SSE transport"""
    with TestClient(math_app) as client:
        response = client.post(
            "/v1/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "divide", "arguments": {"a": 1, "b": 0}},
                "id": 1,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert "error" in result
        assert result["error"]["code"] == -32603  # Internal error code


def test_sse_streaming_content_types(math_app):
    """Test streaming different content types"""
    with TestClient(math_app) as client:
        # Test text content
        response = client.post(
            "/v1/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "create_message",
                "params": {
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": "test"}]}
                    ],
                    "stream": True,
                },
                "id": 1,
            },
            headers={"Accept": "text/event-stream"},
        )
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("text/event-stream")

        # Test image content (base64 encoded)
        response = client.post(
            "/v1/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "create_message",
                "params": {
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"type": "image", "data": "dGVzdA=="}],
                        }
                    ],
                    "stream": True,
                },
                "id": 1,
            },
            headers={"Accept": "text/event-stream"},
        )
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("text/event-stream")


def test_sse_headers_with_model_info(math_app):
    """Test MCP headers with model information"""
    with TestClient(math_app) as client:
        response = client.post(
            "/v1/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "create_message",
                "params": {
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": "test"}]}
                    ],
                    "model": "test-model",
                },
                "id": 1,
            },
        )
        assert response.status_code == 200
        assert "MCP-Version" in response.headers
        assert "MCP-Latency" in response.headers


def test_sse_streaming_error_handling(math_app):
    """Test error handling during streaming"""
    with TestClient(math_app) as client:
        # Test invalid method
        response = client.post(
            "/v1/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "invalid_function",
                    "arguments": {},
                    "stream": True,
                },
                "id": 1,
            },
            headers={"Accept": "text/event-stream"},
        )
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("text/event-stream")

        # Parse events
        events = []
        current_event = None
        current_data = []

        for line in response.content.decode().split("\n"):
            if not line:
                if current_event and current_data:
                    events.append(
                        {"event": current_event, "data": "\n".join(current_data)}
                    )
                current_event = None
                current_data = []
                continue

            if line.startswith("event:"):
                current_event = line[6:].strip()
            elif line.startswith("data:"):
                current_data.append(line[5:].strip())

        # Should have endpoint and error message
        assert len(events) >= 2
        assert events[0]["event"] == "endpoint"

        # Error message should be properly formatted
        assert events[1]["event"] == "message"
        error_data = json.loads(events[1]["data"])
        assert "error" in error_data
        assert error_data["error"]["code"] == -32601  # Method not found error

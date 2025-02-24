from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, TypeAlias

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from hype.function import Function
from hype.mcp.jsonrpc import (
    JsonRpcRequest,
    JsonRpcResponse,
    handle_jsonrpc_request,
)


class Role(str, Enum):
    """Role of a message participant."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class TextContent(BaseModel):
    """Text content for a message."""

    type: Literal["text"] = "text"
    text: str


class ImageContent(BaseModel):
    """Image content for a message."""

    type: Literal["image"] = "image"
    data: str = Field(
        ...,
        description="The base64-encoded image data",
        json_schema_extra={"format": "byte"},
    )


Content: TypeAlias = TextContent | ImageContent


class CreateMessageResult(BaseModel):
    """Result of creating a message."""

    role: Role
    content: Content
    model: str
    stop_reason: str | None = None


def format_sse(event: str, data: str) -> str:
    """Format a server-sent event."""
    return f"event: {event}\ndata: {data}\n\n"


def calculate_mcp_latency(start_time: datetime) -> str:
    """Calculate MCP latency in milliseconds from a start time.

    Args:
        start_time: The start time in UTC

    Returns:
        String representation of latency in milliseconds
    """
    return str(int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000))


def create_mcp_sse_app(
    functions: list[Function],
    title: str = "Hype API",
    summary: str | None = None,
    description: str = "",
    version: str = "0.1.0",
) -> FastAPI:
    """Create a FastAPI application with Model Context Protocol (MCP) support.

    Args:
        functions: List of functions to expose as endpoints
        title: API title
        summary: API summary
        description: API description
        version: API version

    Returns:
        FastAPI application with MCP support
    """
    app = FastAPI(
        title=title,
        summary=summary,
        description=description,
        version=version,
    )

    @app.post("/v1/jsonrpc")
    async def endpoint(request: Request, jsonrpc: JsonRpcRequest) -> Response:
        """Handler for JSON-RPC requests."""
        start_time = datetime.now(timezone.utc)

        # Handle streaming requests
        if jsonrpc.params.get("stream"):

            async def event_generator() -> AsyncGenerator[str, None]:
                # Send initial endpoint event
                yield format_sse("endpoint", str(request.url_for("endpoint")))

                try:
                    response = await handle_jsonrpc_request(jsonrpc, functions)
                    yield format_sse("message", response.model_dump_json())
                except Exception as e:
                    error_response = JsonRpcResponse(
                        jsonrpc="2.0",
                        error={"code": -32603, "message": str(e)},
                        id=jsonrpc.id,
                    )
                    yield format_sse("message", error_response.model_dump_json())

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "MCP-Version": "2024-11-05",
                    "MCP-Stream": "true",
                    "MCP-Latency": calculate_mcp_latency(start_time),
                },
            )

        # Handle regular requests
        try:
            response = await handle_jsonrpc_request(jsonrpc, functions)
            return Response(
                content=response.model_dump_json(),
                media_type="application/json",
                headers={
                    "MCP-Version": "2024-11-05",
                    "MCP-Latency": calculate_mcp_latency(start_time),
                },
            )
        except Exception as e:
            error_response = JsonRpcResponse(
                jsonrpc="2.0", error={"code": -32603, "message": str(e)}, id=jsonrpc.id
            )
            return Response(
                content=error_response.model_dump_json(),
                media_type="application/json",
                headers={
                    "MCP-Version": "2024-11-05",
                    "MCP-Latency": calculate_mcp_latency(start_time),
                },
            )

    return app

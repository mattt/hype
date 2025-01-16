import asyncio
from typing import Any, Literal

from pydantic import BaseModel, Field

from hype.function import Function


class JsonRpcException(Exception):
    """Base class for JSON-RPC errors."""

    def __init__(self, code: int, message: str, data: Any | None = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)

    def to_error(self) -> "JsonRpcError":
        """Convert exception to JSON-RPC error object."""
        return JsonRpcError(code=self.code, message=self.message, data=self.data)


class ParseError(JsonRpcException):
    """Invalid JSON was received by the server."""

    def __init__(self, message: str, data: Any | None = None):
        super().__init__(-32700, f"Parse error: {message}", data)


class InvalidRequest(JsonRpcException):
    """The JSON sent is not a valid Request object."""

    def __init__(self, message: str, data: Any | None = None):
        super().__init__(-32600, f"Invalid Request: {message}", data)


class MethodNotFound(JsonRpcException):
    """The method does not exist / is not available."""

    def __init__(self, method: str, data: Any | None = None):
        super().__init__(-32601, f"Method not found: {method}", data)


class InvalidParams(JsonRpcException):
    """Invalid method parameters."""

    def __init__(self, message: str, data: Any | None = None):
        super().__init__(-32602, f"Invalid params: {message}", data)


class InternalError(JsonRpcException):
    """Internal JSON-RPC error."""

    def __init__(self, message: str, data: Any | None = None):
        super().__init__(-32603, f"Internal error: {message}", data)


class JsonRpcRequest(BaseModel):
    """JSON-RPC request object."""

    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: dict[str, Any]
    id: str | int | None = None


class JsonRpcError(BaseModel):
    """JSON-RPC error object."""

    code: int
    message: str
    data: Any | None = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC response object."""

    jsonrpc: Literal["2.0"] = "2.0"
    result: Any | None = None
    error: JsonRpcError | None = None
    id: str | int | None = None


class CallToolRequest(BaseModel):
    """Request to call a tool."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


async def handle_jsonrpc_request(
    request: JsonRpcRequest, functions: list[Function]
) -> JsonRpcResponse:
    """Handle a JSON-RPC request.

    Args:
        request: The JSON-RPC request to handle
        functions: List of functions available to the request

    Returns:
        JSON-RPC response
    """
    try:
        if request.method == "tools/list":
            return JsonRpcResponse(
                result=[
                    {
                        "name": f.name,
                        "description": f._wrapped.__doc__ or "",
                        "parameters": f.input_schema.get("properties", {}),
                    }
                    for f in functions
                ],
                id=request.id,
            )
        elif request.method == "tools/call":
            try:
                params = CallToolRequest(**request.params)
            except Exception as e:
                raise InvalidParams(str(e))

            function = next((f for f in functions if f.name == params.name), None)
            if not function:
                raise MethodNotFound(params.name)

            try:
                # Call the function with the provided arguments
                if asyncio.iscoroutinefunction(function._wrapped):
                    result = await function(**params.arguments)
                else:
                    result = function(**params.arguments)
                    if asyncio.iscoroutine(result):
                        result = await result

                return JsonRpcResponse(
                    result={
                        "content": [
                            {
                                "type": "text",
                                "text": str(result) if result is not None else "",
                            }
                        ]
                    },
                    id=request.id,
                )
            except Exception as e:
                # Pass through InvalidParams for validation errors
                if isinstance(e, (ValueError, TypeError)):
                    raise InvalidParams(str(e))
                # Convert other exceptions to InternalError with the error message
                error = InternalError(str(e))
                return JsonRpcResponse(error=error.to_error(), id=request.id)
        else:
            raise MethodNotFound(request.method)

    except JsonRpcException as e:
        return JsonRpcResponse(error=e.to_error(), id=request.id)
    except Exception as e:
        error = InternalError(str(e))
        return JsonRpcResponse(error=error.to_error(), id=request.id)

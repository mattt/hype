import asyncio
import json
import sys
from collections.abc import AsyncGenerator
from typing import BinaryIO, TextIO

from hype.function import Function
from hype.mcp.jsonrpc import (
    InternalError,
    JsonRpcException,
    JsonRpcRequest,
    JsonRpcResponse,
    ParseError,
    handle_jsonrpc_request,
)


def _write_response(
    response: JsonRpcResponse, output_stream: TextIO | BinaryIO
) -> None:
    print(response.model_dump_json(), file=output_stream, flush=True)


async def create_mcp_stdio_handler(
    functions: list[Function],
    input_stream: TextIO | BinaryIO = sys.stdin,
    output_stream: TextIO | BinaryIO = sys.stdout,
) -> AsyncGenerator[JsonRpcResponse, None]:
    """Create an MCP handler that reads from stdin and writes to stdout.

    Args:
        functions: List of functions to expose
        input_stream: Input stream to read from (defaults to sys.stdin)
        output_stream: Output stream to write to (defaults to sys.stdout)

    Yields:
        JsonRpcResponse objects for each request processed
    """
    loop = asyncio.get_event_loop()

    while True:
        request = None  # Initialize request variable
        try:
            # Read a line asynchronously
            line = await loop.run_in_executor(None, input_stream.readline)
            if not line:
                break

            line = line.strip()
            if not line:  # Skip empty lines
                continue

            # Parse the request
            try:
                request_data = json.loads(line)
                request = JsonRpcRequest(**request_data)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                response = JsonRpcResponse(error=ParseError(str(e)).to_error(), id=None)
                await loop.run_in_executor(
                    None, _write_response, response, output_stream
                )
                yield response
                continue

            # Handle the request
            response = await handle_jsonrpc_request(request, functions)

            # Write response asynchronously
            await loop.run_in_executor(None, _write_response, response, output_stream)
            yield response

        except JsonRpcException as e:
            response = JsonRpcResponse(
                error=e.to_error(), id=request.id if request is not None else None
            )
            await loop.run_in_executor(None, _write_response, response, output_stream)
            yield response

        except Exception as e:
            if isinstance(e, UnicodeDecodeError):
                error = ParseError(str(e))
            else:
                error = InternalError(str(e))
            response = JsonRpcResponse(
                error=error.to_error(), id=request.id if request is not None else None
            )
            await loop.run_in_executor(None, _write_response, response, output_stream)
            yield response

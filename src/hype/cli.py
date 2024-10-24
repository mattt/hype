import importlib.util
import os
import sys
from typing import Any

import click
import uvicorn

from hype import Function, create_fastapi_app

# Global variable to store the module path
_module_path: str | None = None


def import_module_from_path(path: str) -> Any:
    """Import a Python module from a file path."""
    module_name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise click.ClickException(f"Could not load module from {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def find_functions(module: Any) -> list[Function]:
    """Find all Function instances in a module."""
    functions = []
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, Function):
            functions.append(attr)
    return functions


@click.group()
def cli() -> None:
    """Hype CLI - Serve your functions as an API."""
    pass


@cli.command()
@click.argument("module_path", type=click.Path(exists=True))
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=4973, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
def serve(module_path: str, host: str, port: int, reload: bool) -> None:
    """Serve functions from a Python module as a FastAPI application."""
    try:
        # Store the module path globally
        global _module_path
        _module_path = os.path.abspath(module_path)

        module = import_module_from_path(_module_path)
        functions = find_functions(module)

        if not functions:
            raise click.ClickException(
                f"No hype functions found in {module_path}. "
                "Make sure your functions are decorated with @hype.up"
            )

        app = create_fastapi_app(functions)
        uvicorn.run("hype.cli:app", host=host, port=port, reload=reload, factory=True)
    except Exception as e:
        raise click.ClickException(str(e)) from e


# Factory function for uvicorn
def app() -> Any:
    """Create the FastAPI application (used by uvicorn)."""
    if _module_path is None:
        raise RuntimeError("Module path not set")

    module = import_module_from_path(_module_path)
    functions = find_functions(module)
    return create_fastapi_app(functions)


if __name__ == "__main__":
    cli()

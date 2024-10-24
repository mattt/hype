import importlib.util
import os
import sys
from typing import Any

import click
import uvicorn
from fastapi import FastAPI

from hype import Function, create_fastapi_app


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


def get_reload_dirs(module_path: str) -> list[str]:
    """Get directories to watch for reload."""
    # Watch the module file itself
    module_dir = os.path.dirname(os.path.abspath(module_path))

    # Get the project root (where the module is located)
    project_root = os.path.abspath(os.getcwd())

    # Always watch the module directory and project root
    dirs = [
        module_dir,
        project_root,
    ]

    # Watch src directory if it exists
    src_dir = os.path.join(project_root, "src")
    if os.path.exists(src_dir):
        dirs.append(src_dir)

    # Remove duplicates while preserving order
    unique_dirs = list(dict.fromkeys(dirs))

    click.echo(f"Watching directories for changes: {unique_dirs}")
    return unique_dirs


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    print("Creating app")

    module_path = os.environ.get("HYPE_MODULE_PATH")
    if module_path is None:
        raise RuntimeError("HYPE_MODULE_PATH environment variable not set")

    module = import_module_from_path(module_path)
    functions = find_functions(module)
    print(f"Found {len(functions)} functions")
    if not functions:
        raise click.ClickException(
            f"No hype functions found in {module_path}. "
            "Make sure your functions are decorated with @hype.up"
        )
    return create_fastapi_app(functions)


@click.group()
def cli() -> None:
    """Hype CLI - Serve your functions as an API."""
    pass


@cli.command()
@click.argument("module_path", type=click.Path(exists=True))
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=4973, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
@click.option(
    "--reload-dir",
    multiple=True,
    help="Extra directories to watch for changes when reload is enabled",
)
def serve(
    module_path: str,
    host: str,
    port: int,
    reload: bool,
    reload_dir: tuple[str, ...],
) -> None:
    """Serve functions from a Python module as a FastAPI application."""
    try:
        module_dir = os.path.dirname(os.path.abspath(module_path))
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)

        os.environ["HYPE_MODULE_PATH"] = os.path.abspath(module_path)

        reload_dirs = get_reload_dirs(module_path)
        if reload_dir:
            reload_dirs.extend(reload_dir)

        uvicorn.run(
            "hype.cli:create_app",
            host=host,
            port=port,
            reload=reload,
            reload_dirs=reload_dirs if reload else None,
            factory=True,
        )
    except Exception as e:
        raise click.ClickException(str(e)) from e


if __name__ == "__main__":
    cli()

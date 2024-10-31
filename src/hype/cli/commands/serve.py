import os
import sys

import click
import uvicorn
from fastapi import FastAPI

from hype import create_fastapi_app
from hype.cli.utils import find_functions, get_reload_dirs, import_module_from_path


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    click.echo("Loading module...")
    module_path = os.environ.get("HYPE_MODULE_PATH")
    if module_path is None:
        raise RuntimeError("HYPE_MODULE_PATH environment variable not set")

    module = import_module_from_path(module_path)
    functions = find_functions(module)

    if not functions:
        raise click.ClickException(
            f"No hype functions found in {module_path}.\n"
            "Make sure your functions are decorated with @hype.up"
        )

    function_count = len(functions)
    click.echo(
        f"✓ Found {function_count} {'function' if function_count == 1 else 'functions'}"
    )
    click.echo("✓ API server ready")
    return create_fastapi_app(functions)


@click.command()
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
    """Serve functions from a Python module as a FastAPI application.

    The server watches for file changes and automatically reloads when files are modified.

    Examples:
      # Start server on default port 4973
      hype serve path/to/module.py

      # Start on custom port with auto-reload disabled
      hype serve path/to/module.py --port 8000 --no-reload
    """
    try:
        if not os.path.isfile(module_path):
            raise click.ClickException(f"File not found: {module_path}")

        module_dir = os.path.dirname(os.path.abspath(module_path))
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)

        os.environ["HYPE_MODULE_PATH"] = os.path.abspath(module_path)

        reload_dirs = get_reload_dirs(module_path)
        if reload_dir:
            reload_dirs.extend(reload_dir)
        click.echo(f"Watching directories for changes: {reload_dirs}")

        click.echo(f"Starting server at http://{host}:{port}")

        uvicorn.run(
            "hype.cli.commands.serve:create_app",
            host=host,
            port=port,
            reload=reload,
            reload_dirs=reload_dirs if reload else None,
            factory=True,
        )
    except Exception as e:
        raise click.ClickException(str(e)) from e

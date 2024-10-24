import importlib.util
import os
import sys
from typing import Any

import click
import uvicorn
from pydantic import BaseModel

from hype import Function


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


class FunctionCommand(click.Command):
    """Custom command class for function invocation."""

    def __init__(self, function: Function, **kwargs: Any) -> None:
        self.function = function

        # Get help text from function description and input schema
        help_text = function.description or ""
        if help_text:
            help_text += "\n\n"

        # Add parameter descriptions from input schema
        schema = function.input_schema
        if "properties" in schema:
            help_text += "Parameters:\n"
            for name, prop in schema["properties"].items():
                description = prop.get("description", "No description")
                help_text += f"  {name}: {description}\n"

        super().__init__(
            name=function.name, help=help_text, callback=self.invoke_function, **kwargs
        )

        # Add options based on function parameters
        for name, prop in schema.get("properties", {}).items():
            param_type = str  # Default to string type
            if prop.get("type") == "integer":
                param_type = int
            elif prop.get("type") == "number":
                param_type = float
            elif prop.get("type") == "boolean":
                param_type = bool

            self.params.append(
                click.Option(
                    ["--" + name],
                    type=param_type,
                    required=name in schema.get("required", []),
                    help=prop.get("description"),
                )
            )

    def invoke_function(self, **kwargs: Any) -> None:
        """Execute the wrapped function with provided arguments."""
        try:
            result = self.function(**kwargs)
            if isinstance(result, BaseModel):
                result = result.model_dump()
            click.echo(result)
        except Exception as e:
            raise click.ClickException(str(e)) from e


class ModuleGroup(click.Group):
    """Custom group class that loads commands from a module."""

    def __init__(self, module_path: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.module_path = module_path
        self._loaded = False
        self._functions: list[Function] = []

    def _load_commands(self) -> None:
        """Lazy load commands from the module."""
        if self._loaded:
            return

        module = import_module_from_path(self.module_path)
        self._functions = find_functions(module)

        for function in self._functions:
            self.add_command(FunctionCommand(function))

        self._loaded = True

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        self._load_commands()
        return super().get_command(ctx, cmd_name)

    def list_commands(self, ctx: click.Context) -> list[str]:
        self._load_commands()
        return sorted(self.commands)


@click.group()
def cli() -> None:
    """Hype CLI - Serve or run your functions."""
    pass


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("module_path", type=click.Path(exists=True))
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run(module_path: str, args: tuple[str, ...]) -> None:
    """Run a function from a Python module.

    If no function is specified, lists available functions.
    """
    try:
        module_dir = os.path.dirname(os.path.abspath(module_path))
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)

        # Create a command group for the module
        group = ModuleGroup(
            module_path=module_path,
            name=os.path.basename(module_path),
            help="Available functions in this module.",
        )

        if not args:
            # Show available functions if no function specified
            with click.Context(group) as ctx:
                click.echo(group.get_help(ctx))
            return

        # Run the specified function with remaining args
        ctx = click.Context(group)
        cmd_name = args[0]
        cmd = group.get_command(ctx, cmd_name)
        if cmd is None:
            raise click.ClickException(f"No such command: {cmd_name}")

        remaining_args = list(args[1:])
        if not remaining_args:
            # Show help for the specified function if no arguments are provided
            with click.Context(cmd) as cmd_ctx:
                click.echo(cmd.get_help(cmd_ctx))
            return

        with ctx:
            return cmd.main(args=remaining_args, standalone_mode=False)

    except Exception as e:
        raise click.ClickException(str(e)) from e


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

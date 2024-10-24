import os
import sys
from typing import Any

import click
from pydantic import BaseModel

from hype import Function
from hype.cli.utils import find_functions, import_module_from_path


class FunctionCommand(click.Command):
    """Custom command class for function invocation."""

    def __init__(self, function: Function, **kwargs: Any) -> None:
        self.function = function
        help_text = function.description or ""
        if help_text:
            help_text += "\n\n"
        schema = function.input_schema
        if "properties" in schema:
            help_text += "Parameters:\n"
            for name, prop in schema["properties"].items():
                description = prop.get("description", "No description")
                help_text += f"  {name}: {description}\n"
        super().__init__(
            name=function.name, help=help_text, callback=self.invoke_function, **kwargs
        )
        for name, prop in schema.get("properties", {}).items():
            param_type = str
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


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("module_path", type=click.Path(exists=True))
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run(module_path: str, args: tuple[str, ...]) -> None:
    """Run a function from a Python module."""
    try:
        module_dir = os.path.dirname(os.path.abspath(module_path))
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)

        group = ModuleGroup(
            module_path=module_path,
            name=os.path.basename(module_path),
            help="Available functions in this module.",
        )

        if not args:
            with click.Context(group) as ctx:
                click.echo(group.get_help(ctx))
            return

        ctx = click.Context(group)
        cmd_name = args[0]
        cmd = group.get_command(ctx, cmd_name)
        if cmd is None:
            raise click.ClickException(f"No such command: {cmd_name}")

        remaining_args = list(args[1:])
        if not remaining_args:
            with click.Context(cmd) as cmd_ctx:
                click.echo(cmd.get_help(cmd_ctx))
            return

        with ctx:
            return cmd.main(args=remaining_args, standalone_mode=False)

    except Exception as e:
        raise click.ClickException(str(e)) from e

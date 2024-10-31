import os
import sys
from difflib import get_close_matches
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

        # Add all parameters as options that can be used both positionally and with flags
        required_params = schema.get("required", [])
        for name, prop in schema.get("properties", {}).items():
            self._append_option(name, prop, required=(name in required_params))

    def _append_option(self, name: str, prop: dict, required: bool) -> None:
        """Add a click Option to the command's parameters.

        Args:
            name: Parameter name
            prop: Parameter properties from the schema
            required: Whether the parameter is required
        """
        param_type = self._get_param_type(prop)
        self.params.append(
            click.Option(
                ["--" + name],
                type=param_type,
                required=required,
                is_flag=False,
                help=prop.get("description"),
            )
        )

    def _get_param_type(self, prop: dict) -> Any:
        """Helper method to determine parameter type."""
        param_type = str
        if prop.get("type") == "integer":
            param_type = int
        elif prop.get("type") == "number":
            param_type = float
        elif prop.get("type") == "boolean":
            param_type = bool
        return param_type

    def parse_args(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[list[str], list[str], list[str]]:
        """Override to handle positional arguments for required parameters."""
        # Handle the -- separator
        if "--" in args:
            idx = args.index("--")
            before_sep = args[:idx]
            after_sep = args[idx + 1 :]
            # Convert everything after -- into a single positional argument
            if after_sep:
                args = before_sep + [" ".join(after_sep)]
            else:
                args = before_sep

        # Split args into positional and named
        positional = []
        named = []

        i = 0
        while i < len(args):
            arg = args[i]
            if arg.startswith("-"):
                named.append(arg)
                if i + 1 < len(args) and not args[i + 1].startswith("-"):
                    named.append(args[i + 1])
                    i += 1
            else:
                positional.append(arg)
            i += 1

        # Map positional args to required parameters in order
        required_params = [p for p in self.params if p.required]
        if len(positional) > len(required_params):
            raise click.UsageError(
                f"Got unexpected extra argument ({' '.join(positional[len(required_params):])})"
            )

        # Convert positional args into named args
        for param, value in zip(required_params, positional, strict=False):
            named.extend([f"--{param.name}", value])

        return super().parse_args(ctx, named)

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
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None and self._functions:
            # Get list of available function names
            available_commands = list(self.commands.keys())
            # Find similar commands using difflib
            suggestions = get_close_matches(
                cmd_name, available_commands, n=3, cutoff=0.6
            )
            if suggestions:
                suggestion_msg = "\nDid you mean one of these?\n    " + "\n    ".join(
                    suggestions
                )
                ctx.fail(f"No such command: {cmd_name}{suggestion_msg}")
        return cmd

    def list_commands(self, ctx: click.Context) -> list[str]:
        self._load_commands()
        return sorted(self.commands)


@click.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
@click.argument("module_path", type=click.Path(exists=True), required=False)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run(module_path: str | None, args: tuple[str, ...]) -> None:
    """Run a function from a Python module.

    MODULE_PATH is the path to your Python module containing functions.
    Any additional arguments will be passed to the specified function.
    """
    if module_path is None:
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        ctx.exit()

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

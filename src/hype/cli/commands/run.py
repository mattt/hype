import json
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
        self.output_file = kwargs.pop("output_file", None)

        help_text = function.description or ""

        super().__init__(
            name=function.name, help=help_text, callback=self.invoke_function, **kwargs
        )

        # Add built-in options first
        self.params.append(
            click.Option(
                ["--output"],
                type=click.Path(writable=True),
                required=False,
                help="Write output to a JSON file",
                is_flag=False,
            )
        )

        # Add function-specific parameters as options
        schema = function.input_schema  # Get schema from the function object
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
                default=prop.get("default"),
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
        used_param_names = set()  # Track which parameters have been used

        for i, arg in enumerate(args):
            if arg.startswith("-"):
                named.append(arg)
                param_name = arg.lstrip("-")
                used_param_names.add(param_name)
                # Check if next arg exists and is a value (not a flag)
                if i + 1 < len(args) and not args[i + 1].startswith("-"):
                    named.append(args[i + 1])
            elif i > 0 and args[i - 1].startswith("-"):
                # Skip values that were already handled as part of a named arg
                continue
            else:
                positional.append(arg)

        # Get function parameters (excluding built-in options)
        function_params = [
            param for param in self.params if param.name not in ["output", "help"]
        ]

        # Check if we have too many positional arguments
        if len(positional) > len(function_params):
            raise click.UsageError(
                f"Got unexpected extra argument ({' '.join(positional[len(function_params):])})"
            )

        # Convert positional args into named args
        for param, value in zip(function_params, positional, strict=False):
            # Check if this parameter was already provided as a named argument
            if param.name in used_param_names:
                raise click.UsageError(f"Got unexpected extra argument ({value})")
            named.extend([f"--{param.name}", value])

        return super().parse_args(ctx, named)

    def invoke_function(self, **kwargs: Any) -> None:
        """Execute the wrapped function with provided arguments."""
        try:
            # Filter out None values for optional parameters
            filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}

            result = self.function(**filtered_kwargs)
            if isinstance(result, BaseModel):
                result = result.model_dump()

            if self.output_file:
                with open(self.output_file, "w") as f:
                    json.dump(result, f, indent=2)
            else:
                click.echo(result)
        except Exception as e:
            raise click.ClickException(str(e)) from e

    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Format the usage line."""

        # Get required parameters
        required_params = [
            param.name.upper()
            for param in self.params
            if param.name not in ["output", "help"] and param.required
        ]

        # Format usage line
        usage = f"{ctx.command.name} [OPTIONS]"
        if required_params:
            usage += " " + " ".join(required_params)

        formatter.write_usage("hype run", usage)

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Custom help formatter to improve the layout."""
        self.format_usage(ctx, formatter)
        self.format_help_text(ctx, formatter)
        self.format_options(ctx, formatter)

    def format_help_text(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Format the help text."""
        if self.help:
            formatter.write_paragraph()
            formatter.write_text(self.help)

    def format_options(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Format the options sections."""
        built_in_opts = []
        function_opts = []

        for param in self.get_params(ctx):
            if param.name in ["output", "help"]:
                built_in_opts.append(param)
            else:
                function_opts.append(param)

        if function_opts:
            with formatter.section("Parameters"):
                with formatter.indentation():
                    for param in function_opts:
                        formatter.write_text(f"--{param.name}")
                        if param.help:
                            with formatter.indentation():
                                formatter.write_text(param.help)
                        if param.required:
                            with formatter.indentation():
                                formatter.write_text("[required]")

        if built_in_opts:
            with formatter.section("Options"):
                with formatter.indentation():
                    for param in built_in_opts:
                        formatter.write_dl([param.get_help_record(ctx)])


class ModuleGroup(click.Group):
    """Custom group class that loads commands from a module."""

    def __init__(
        self, module_path: str, output_file: str | None = None, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.module_path = module_path
        self.output_file = output_file
        self._loaded = False
        self._functions: list[Function] = []

    def _load_commands(self) -> None:
        """Lazy load commands from the module."""
        if self._loaded:
            return
        module = import_module_from_path(self.module_path)
        self._functions = find_functions(module)
        for function in self._functions:
            self.add_command(FunctionCommand(function, output_file=self.output_file))
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
@click.option(
    "--output", type=click.Path(writable=True), help="Write output to a JSON file"
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run(module_path: str | None, output: str | None, args: tuple[str, ...]) -> None:
    """Run a function from a Python module.

    MODULE_PATH is the path to your Python module containing functions.
    Any additional arguments are passed to the specified function.

    The function output can be written to a JSON file using the --output option:

        $ hype run example.py --output results.json my_function --param1 value1

    When --output isn't specified, results are printed to stdout.
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
            output_file=output,
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

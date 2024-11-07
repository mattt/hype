import json
import os
import sys
import textwrap
from collections.abc import Iterator
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path
from typing import Any

import click

from hype import Function
from hype.cli.utils import find_functions, import_module_from_path
from hype.job import Batch, Error, Job, Status


class FunctionCommand(click.Command):
    """Custom command class for function invocation."""

    # Class-level constant (no self needed)
    BUILT_IN_OPTIONS = frozenset(["input", "output", "help"])

    def __init__(self, function: Function, module_path: str, **kwargs: Any) -> None:
        self.function = function
        self.input_file = kwargs.pop("input_file", None)
        self.output_file = kwargs.pop("output_file", None)
        self.module_path = module_path

        help_text = function.description or ""

        super().__init__(
            name=function.name, help=help_text, callback=self.invoke, **kwargs
        )

        # Add built-in options first
        self.params.append(
            click.Option(
                ["--input"],
                type=click.Path(exists=True, readable=True),
                required=False,
                help="Read input from a JSON or JSON Lines file",
                is_flag=False,
            )
        )
        self.params.append(
            click.Option(
                ["--output"],
                type=click.Path(writable=True),
                required=False,
                help="Write output to a JSON or JSON Lines file",
                is_flag=False,
            )
        )

        # Add function-specific parameters as options
        schema = function.input_schema
        required_params = schema.get("required", [])
        for name, prop in schema.get("properties", {}).items():
            # When using --input, all parameters should be optional
            self._append_option(
                name, prop, required=(name in required_params and not self.input_file)
            )

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

        def is_function_arg(arg: str) -> bool:
            """Check if an argument is a function argument (not input/output/etc.)"""
            return arg.startswith("--") and arg not in self.BUILT_IN_OPTIONS

        def extract_option_pairs(
            args: list[str], allowed_options: set[str]
        ) -> list[str]:
            """Extract option-value pairs for specified options."""
            result = []
            for i, arg in enumerate(args):
                if arg in allowed_options and i + 1 < len(args):
                    result.extend([arg, args[i + 1]])
            return result

        # Check for --input and validate arguments
        has_input = "--input" in args
        has_args = any(
            arg for arg in args if is_function_arg(arg) or not arg.startswith("--")
        )

        if has_input and has_args:
            raise click.UsageError(
                "Cannot specify function arguments when using --input"
            )

        # Handle --input case separately
        if has_input:
            return super().parse_args(
                ctx, extract_option_pairs(args, {"--input", "--output"})
            )

        # Handle the -- separator for command arguments
        if "--" in args:
            idx = args.index("--")
            args = (
                args[:idx] + [" ".join(args[idx + 1 :])]
                if args[idx + 1 :]
                else args[:idx]
            )

        # Get function parameters (excluding built-in options)
        function_params = [
            param for param in self.params if param.name not in self.BUILT_IN_OPTIONS
        ]

        # Split args into positional and named arguments
        positional = []
        named = []
        args_iter = iter(enumerate(args))

        for i, arg in args_iter:
            if arg.startswith("--"):
                if i + 1 >= len(args):
                    raise click.UsageError(f"Option {arg} requires an argument")
                named.extend([arg, args[i + 1]])
                next(args_iter, None)  # Skip the next item since we consumed it
            else:
                positional.append(arg)

        # Validate for duplicate parameters
        used_params = set()
        for i in range(0, len(named), 2):
            param_name = named[i][2:]  # Remove '--' prefix
            if param_name in used_params:
                raise click.UsageError(
                    f"Got multiple values for argument '{param_name}'"
                )
            used_params.add(param_name)

        # Validate number of positional arguments
        if len(positional) > len(function_params):
            extra_args = " ".join(positional[len(function_params) :])
            raise click.UsageError(f"Got unexpected extra argument ({extra_args})")

        # Convert positional args into named args
        for param, value in zip(function_params, positional, strict=False):
            if param.name in used_params:
                raise click.UsageError(
                    f"Got multiple values for argument '{param.name}'"
                )
            named.extend([f"--{param.name}", value])
            used_params.add(param.name)

        # Include output option if present
        if "--output" in args:
            named.extend(extract_option_pairs(args, {"--output"}))

        return super().parse_args(ctx, named)

    def _read_input(self, file: str) -> dict | None:
        """Read input from a JSON file."""
        path = Path(file)
        with path.open(encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise click.ClickException("Input file is empty")

            try:
                data = json.loads(content)
                return data
            except json.JSONDecodeError as e:
                raise click.ClickException(f"Invalid JSON in input file: {e}") from e

    def _read_batch_inputs(self, file: str) -> Iterator[dict]:
        """Read inputs from a JSON Lines file."""
        path = Path(file)
        with path.open(encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:  # Skip empty lines
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as e:
                        raise click.ClickException(
                            f"Invalid JSON on line {line_num}: {e}"
                        ) from e

    def _apply_defaults(self, input_data: dict | None = None) -> dict:
        """Apply defaults to function parameters."""
        defaults = {
            name: prop.get("default")
            for name, prop in self.function.input_schema.get("properties", {}).items()
            if "default" in prop
        }
        if input_data:
            defaults.update(input_data)
        return defaults

    def invoke(self, ctx: click.Context) -> None:
        """Execute the wrapped function with provided arguments."""
        input_file = ctx.params.pop("input", None) or self.input_file
        output_file = ctx.params.pop("output", None) or self.output_file

        if input_file and input_file.endswith(".jsonl"):
            # Read batch of inputs from a JSON Lines file
            jobs = [Job(input=input) for input in self._read_batch_inputs(input_file)]
            for job in jobs:
                self._execute(job)

            batch = Batch(jobs=jobs)
            self._write_batch_output(batch, output_file)
        else:
            # Process single input from a JSON file or CLI arguments
            input = self._read_input(input_file) if input_file else ctx.params
            job = Job(input=self._apply_defaults(input))
            self._execute(job)
            self._write_job_output(job, output_file)

            if job.status == Status.FAILURE:
                raise click.ClickException(job.error.message)

    def _execute(self, job: Job) -> Job:
        try:
            job.started_at = datetime.now(timezone.utc)
            job.output = self.function(**job.input)
        except Exception as e:  # pylint: disable=broad-exception-caught
            job.error = Error(message=str(e))
        finally:
            job.completed_at = datetime.now(timezone.utc)
        return job

    def _write_batch_output(
        self, batch: Batch[dict, Any], output_file: str | None
    ) -> None:
        """Write batch results to output file or stdout."""
        if output_file:
            with click.open_file(output_file, "w", encoding="utf-8") as f:
                if output_file.endswith(".jsonl"):
                    for job in batch.jobs:
                        f.write(json.dumps(job.model_dump(), default=str) + "\n")
                else:
                    outputs = [job.model_dump() for job in batch.jobs]
                    f.write(json.dumps(outputs, default=str) + "\n")
        else:
            for job in batch.jobs:
                self._write_job_output_to_stdout(job)

    def _write_job_output(self, job: Job[dict, Any], output_file: str | None) -> None:
        """Write single job result to output file or stdout."""
        if output_file:
            with click.open_file(output_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(job.model_dump(), default=str) + "\n")
        else:
            self._write_job_output_to_stdout(job)

    def _write_job_output_to_stdout(self, job: Job[dict, Any]) -> None:
        """Write job output to stdout."""

        if job.status == Status.SUCCESS:
            output = job.output
            if output is None:
                click.echo("No output", err=True)
            elif isinstance(output, dict | list):
                click.echo(json.dumps(output, default=str))
            else:
                click.echo(output)

    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Format the usage line."""

        # Build the full command path including the complete module path
        command_path = f"hype run {self.module_path} {self.name}"
        prefix = f"Usage: {command_path} "
        formatter.write(prefix)

        # Write the options section
        formatter.write("[options...]")

        # Get required parameters
        if parameters := [
            param for param in self.params if param.name not in self.BUILT_IN_OPTIONS
        ]:
            for param in parameters:
                formatter.write(" \\ \n")
                chunk = f"(<{param.name}> | --{param.name} VALUE)"
                if not param.required:
                    chunk = f"[{chunk}]"
                formatter.write(" " * len(prefix) + chunk)

        formatter.write("\n")

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
            if param.name in self.BUILT_IN_OPTIONS:
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
        self,
        module_path: str,
        input_file: str | None = None,
        output_file: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Store full module path
        self.full_module_path = module_path
        # Use basename for the name to keep display clean
        kwargs["name"] = os.path.basename(module_path)
        super().__init__(**kwargs)
        self.module_path = module_path
        self.input_file = input_file
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
            self.add_command(
                FunctionCommand(
                    function,
                    module_path=self.module_path,
                    output_file=self.output_file,
                    input_file=self.input_file,
                )
            )
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
                ctx.fail(
                    f"No such command: {cmd_name}\n"
                    f"Did you mean one of these?\n"
                    f"{textwrap.indent('\n'.join(suggestions), '    ')}"
                )
        return cmd

    def list_commands(self, ctx: click.Context) -> list[str]:
        self._load_commands()
        return sorted(self.commands)


@click.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
@click.argument("module_path", type=click.Path(exists=True), required=False)
@click.option(
    "--input",
    type=click.Path(exists=True, readable=True),
    help="Read input from a JSON or JSON Lines file",
)
@click.option(
    "--output", type=click.Path(writable=True), help="Write output to a JSON file"
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run(
    module_path: str | None,
    output: str | None,
    input: str | None,
    args: tuple[str, ...],
) -> None:
    """Run a function from a Python module.

    MODULE_PATH is the path to your Python module containing functions.
    Any additional arguments are passed to the specified function.

    The function output can be written to a JSON file using the --output option:

        $ hype run example.py --output results.json my_function --param1 value1

    Input can be provided from a JSON or JSON Lines file using the --input option:

        $ hype run example.py --input input.jsonl --output results.jsonl my_function

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

        if input is not None and len(args) > 1:  # args[0] is the command name
            # Check if any remaining args are function arguments
            function_args = [arg for arg in args[1:] if arg != "--output"]
            if function_args:
                raise click.UsageError(
                    "Cannot specify function arguments when using --input"
                )

        group = ModuleGroup(
            module_path=module_path,
            input_file=input,
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
        if not remaining_args and not input:  # Only show help if no input file
            with click.Context(cmd) as cmd_ctx:
                click.echo(cmd.get_help(cmd_ctx))
            return

        with ctx:
            return cmd.main(args=remaining_args, standalone_mode=False)

    except Exception as e:
        if not isinstance(e, click.ClickException):
            raise click.ClickException(str(e)) from e
        raise

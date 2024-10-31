import click

from hype.cli.commands import run, serve


@click.group()
def cli() -> None:
    """Hype - Run and serve Python functions.

    Examples:
      # Run a function directly
      hype run example.py my_function --arg1 value1

      # Start API server
      hype serve example.py --port 8000
    """


cli.add_command(run)
cli.add_command(serve)

if __name__ == "__main__":
    cli()

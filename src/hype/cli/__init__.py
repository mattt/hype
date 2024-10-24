import click

from hype.cli.commands import run, serve


@click.group()
def cli() -> None:
    """Hype CLI - Serve or run your functions."""


cli.add_command(run)
cli.add_command(serve)

if __name__ == "__main__":
    cli()

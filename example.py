import hype


@hype.up
def hello(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"


@hype.up
def fail() -> None:
    """Intentionally raises an exception"""
    raise Exception("Something went wrong")

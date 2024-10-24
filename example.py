import hype

@hype.up
def hello(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"

from click.testing import CliRunner

from hype.cli.commands.run import run


def setup_test_module(tmp_path):
    """Create a test module with simple functions for testing."""
    module_path = tmp_path / "test_module.py"
    module_path.write_text("""
from typing import Annotated
import hype

@hype.up
def greet(name: str, title: str = "Dr.") -> str:
    '''Greet someone with their title.

    Args:
        name: Name of the person to greet
        title: Title to use (default: Dr.)
    '''
    return f"Hello {title} {name}!"

@hype.up
def concat(first: str, second: str) -> str:
    '''Concatenate two strings.

    Args:
        first: First string
        second: Second string
    '''
    return first + second
""")
    return module_path


def test_required_args_as_positional(tmp_path):
    """Test passing required arguments positionally."""
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(run, [str(module_path), "concat", "hello", "world"])
    assert result.exit_code == 0
    assert result.output == "helloworld\n"


def test_required_args_as_named(tmp_path):
    """Test passing required arguments by name."""
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        run, [str(module_path), "concat", "--first", "hello", "--second", "world"]
    )
    assert result.exit_code == 0
    assert result.output == "helloworld\n"


def test_mixed_positional_and_named_args(tmp_path):
    """Test mixing positional and named arguments."""
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        run, [str(module_path), "concat", "hello", "--second", "world"]
    )
    assert result.exit_code == 0
    assert result.output == "helloworld\n"


def test_optional_parameters(tmp_path):
    """Test handling of optional parameters with defaults."""
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    # Test with default value
    result = runner.invoke(run, [str(module_path), "greet", "Alice"])
    assert result.exit_code == 0
    assert result.output == "Hello Dr. Alice!\n"

    # Test with provided value
    result = runner.invoke(run, [str(module_path), "greet", "Bob", "--title", "Mr."])
    assert result.exit_code == 0
    assert result.output == "Hello Mr. Bob!\n"


def test_separator_handling(tmp_path):
    """Test handling of the -- separator."""
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(run, [str(module_path), "concat", "--", "hello", "world"])
    assert result.exit_code == 0
    assert result.output == "helloworld\n"


def test_error_missing_required_arg(tmp_path):
    """Test error handling for missing required arguments."""
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(run, [str(module_path), "concat", "--second", "world"])
    assert result.exit_code != 0
    assert result.output.endswith("Error: Missing parameter: first\n")


def test_error_extra_args(tmp_path):
    """Test error handling for extra unexpected arguments."""
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(run, [str(module_path), "greet", "Eve", "Dr", "extra"])
    assert result.exit_code != 0
    assert result.output.endswith("Error: Got unexpected extra argument (extra)\n")


def test_error_ambiguous_args(tmp_path):
    """Test error handling for ambiguous argument usage."""
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        run, [str(module_path), "greet", "Frank", "--name", "George"]
    )
    assert result.exit_code != 0
    assert result.output.endswith("Error: Got unexpected extra argument (Frank)\n")

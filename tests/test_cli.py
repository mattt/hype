import threading
import time

import httpx
from click.testing import CliRunner

from hype.cli.commands.run import run
from hype.cli.commands.serve import serve


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


def test_run_required_args_as_positional(tmp_path):
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(run, [str(module_path), "concat", "hello", "world"])
    assert result.exit_code == 0
    assert result.output == "helloworld\n"


def test_run_required_args_as_named(tmp_path):
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        run, [str(module_path), "concat", "--first", "hello", "--second", "world"]
    )
    assert result.exit_code == 0
    assert result.output == "helloworld\n"


def test_run_mixed_positional_and_named_args(tmp_path):
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        run, [str(module_path), "concat", "hello", "--second", "world"]
    )
    assert result.exit_code == 0
    assert result.output == "helloworld\n"


def test_run_optional_parameters(tmp_path):
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


def test_run_separator_handling(tmp_path):
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(run, [str(module_path), "concat", "--", "hello", "world"])
    assert result.exit_code == 0
    assert result.output == "helloworld\n"


def test_run_error_missing_required_arg(tmp_path):
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(run, [str(module_path), "concat", "--second", "world"])
    assert result.exit_code != 0
    assert result.output.endswith("Error: Missing parameter: first\n")


def test_run_error_extra_args(tmp_path):
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(run, [str(module_path), "greet", "Eve", "Dr", "extra"])
    assert result.exit_code != 0
    assert result.output.endswith("Error: Got unexpected extra argument (extra)\n")


def test_run_error_ambiguous_args(tmp_path):
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        run, [str(module_path), "greet", "Frank", "--name", "George"]
    )
    assert result.exit_code != 0
    assert result.output.endswith("Error: Got unexpected extra argument (Frank)\n")


def test_serve_functional(tmp_path, mocker):
    """Test that serve command creates a working API server."""
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    # Start server in a separate thread
    server_thread = threading.Thread(
        target=lambda: runner.invoke(
            serve,
            [
                str(module_path),
                "--host",
                "127.0.0.1",
                "--port",
                "49732",  # Using different port for test
            ],
        )
    )
    server_thread.daemon = True
    server_thread.start()

    # Poll for server availability instead of fixed sleep
    start_time = time.time()
    while time.time() - start_time < 10:  # timeout after 10 seconds
        try:
            httpx.get("http://127.0.0.1:49732/openapi.json")
            break  # Server is up if we can connect
        except httpx.ConnectError:
            time.sleep(0.1)  # Short sleep between attempts
    else:
        raise TimeoutError("Server failed to start within 10 seconds")

    try:
        # Test the greet endpoint
        response = httpx.post("http://127.0.0.1:49732/greet", json={"name": "Alice"})
        assert response.status_code == 200
        assert response.json() == "Hello Dr. Alice!"

        # Test the concat endpoint
        response = httpx.post(
            "http://127.0.0.1:49732/concat", json={"first": "hello", "second": "world"}
        )
        assert response.status_code == 200
        assert response.json() == "helloworld"

        # Test OpenAPI docs endpoint
        response = httpx.get("http://127.0.0.1:49732/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "/greet" in schema["paths"]
        assert "/concat" in schema["paths"]

    finally:
        # Wait for server thread to finish with timeout
        server_thread.join(timeout=1)
        if server_thread.is_alive():
            print("Warning: Server thread did not shut down cleanly")


def test_serve_with_custom_options(tmp_path, mocker):
    """Test serve command with custom host, port, and reload options."""
    module_path = setup_test_module(tmp_path)
    runner = CliRunner()

    mock_run = mocker.patch("uvicorn.run")

    result = runner.invoke(
        serve,
        [
            str(module_path),
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--reload",
            "--reload-dir",
            "extra_dir",
        ],
    )

    assert result.exit_code == 0
    mock_run.assert_called_once()
    call_args = mock_run.call_args[1]
    assert call_args["host"] == "0.0.0.0"
    assert call_args["port"] == 8000
    assert call_args["reload"] is True
    assert isinstance(call_args["reload_dirs"], list)
    assert "extra_dir" in call_args["reload_dirs"]

# pylint: disable=redefined-outer-name

import json
import threading
import time

import httpx
import pytest
from click.testing import CliRunner

from hype.cli.commands.run import run
from hype.cli.commands.serve import serve


@pytest.fixture
def temp_module(tmp_path):
    """Create a test module with example functions"""
    module_path = tmp_path / "test_module.py"
    module_path.write_text("""
import hype

@hype.up
def echo(message: str) -> str:
    return message

@hype.up
def add(a: int, b: int, c: int = 0) -> int:
    return a + b + c
""")
    return str(module_path)


@pytest.fixture
def runner():
    return CliRunner()


# Basic CLI argument tests
def test_run_positional_args(runner, temp_module):
    result = runner.invoke(run, [temp_module, "add", "1", "2"])
    if result.exit_code != 0:
        raise AssertionError(f"Command failed with: {result.output}")
    assert result.output == "3\n"


def test_run_named_args(runner, temp_module):
    result = runner.invoke(run, [temp_module, "add", "--a", "1", "--b", "2"])
    if result.exit_code != 0:
        raise AssertionError(f"Command failed with: {result.output}")
    assert result.output == "3\n"


def test_run_optional_args(runner, temp_module):
    result = runner.invoke(run, [temp_module, "add", "1", "2", "--c", "3"])
    if result.exit_code != 0:
        raise AssertionError(f"Command failed with: {result.output}")
    assert result.output == "6\n"


# Error cases
def test_run_missing_required_arg(runner, temp_module):
    result = runner.invoke(run, [temp_module, "add", "--b", "2"])
    assert result.exit_code != 0
    assert "Missing parameter: a" in result.output


def test_run_extra_args(runner, temp_module):
    result = runner.invoke(run, [temp_module, "add", "1", "2", "3", "4"])
    assert result.exit_code != 0
    assert "Got unexpected extra argument" in result.output


def test_run_invalid_function_name(runner, temp_module):
    result = runner.invoke(run, [temp_module, "sad"])
    assert result.exit_code != 0
    assert "No such command: sad" in result.output
    assert "Did you mean one of these?" in result.output  # Should suggest similar names


# File I/O tests
def test_run_with_output_file(runner, temp_module, tmp_path):
    output_file = tmp_path / "output.json"
    result = runner.invoke(
        run, [temp_module, "--output", str(output_file), "add", "1", "2"]
    )
    if result.exit_code != 0:
        raise AssertionError(f"Command failed with: {result.output}")
    assert result.output == ""
    assert json.loads(output_file.read_text()) == 3


def test_run_with_json_input(runner, temp_module, tmp_path):
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"message": "hello"}))
    result = runner.invoke(run, [temp_module, "echo", "--input", str(input_file)])
    if result.exit_code != 0:
        raise AssertionError(f"Command failed with: {result.output}")
    assert json.loads(result.output.strip()) == "hello"


def test_run_with_jsonl_input(runner, temp_module, tmp_path):
    input_file = tmp_path / "input.jsonl"
    input_lines = [
        json.dumps(line)
        for line in [
            {"a": 1, "b": 2, "c": 3},
            {"a": 3, "b": 4},
        ]
    ]
    input_file.write_text("\n".join(input_lines))
    output_file = tmp_path / "output.jsonl"

    result = runner.invoke(
        run,
        [temp_module, "add", "--input", str(input_file), "--output", str(output_file)],
    )
    if result.exit_code != 0:
        raise AssertionError(f"Command failed with: {result.output}")
    outputs = output_file.read_text().strip().split("\n")
    assert json.loads(outputs[0]) == 6  # 1 + 2 + 3
    assert json.loads(outputs[1]) == 7  # 3 + 4


def test_run_empty_input_file(runner, temp_module, tmp_path):
    input_file = tmp_path / "empty.json"
    input_file.write_text("")
    result = runner.invoke(run, [temp_module, "add", "--input", str(input_file)])
    assert result.exit_code != 0
    assert "Input file is empty" in result.output


def test_run_invalid_json_input(runner, temp_module, tmp_path):
    input_file = tmp_path / "invalid.json"
    input_file.write_text("{invalid json}")
    result = runner.invoke(run, [temp_module, "add", "--input", str(input_file)])
    assert result.exit_code != 0
    assert "Invalid JSON" in result.output


def test_run_input_with_args_error(runner, temp_module, tmp_path):
    input_file = tmp_path / "input.json"
    input_file.write_text('{"a": 1, "b": 2}')
    result = runner.invoke(
        run, [temp_module, "add", "--input", str(input_file), "--a", "1"]
    )
    assert result.exit_code != 0
    assert "Cannot specify function arguments when using --input" in result.output


def test_run_duplicate_argument(runner, temp_module):
    result = runner.invoke(
        run, [temp_module, "add", "--a", "1", "--a", "2", "--b", "3"]
    )
    assert result.exit_code != 0
    assert "Got multiple values for argument 'a'" in result.output


def test_run_missing_option_value(runner, temp_module):
    result = runner.invoke(run, [temp_module, "add", "--a"])
    assert result.exit_code != 0
    assert "Option --a requires an argument" in result.output


def test_run_output_with_no_args(runner, temp_module):
    result = runner.invoke(run, [temp_module, "add"])
    assert result.exit_code == 0
    assert "Parameters" in result.output
    assert "--a" in result.output
    assert "--b" in result.output
    assert "--c" in result.output


def test_run_module_help(runner, temp_module):
    result = runner.invoke(run, [temp_module])
    assert result.exit_code == 0
    assert "Available functions in this module" in result.output
    assert "add" in result.output
    assert "echo" in result.output


def test_run_with_json_array_input(runner, temp_module, tmp_path):
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps([{"a": 1, "b": 2}, {"a": 3, "b": 4}]))
    output_file = tmp_path / "output.jsonl"

    result = runner.invoke(
        run,
        [temp_module, "add", "--input", str(input_file), "--output", str(output_file)],
    )
    assert result.exit_code == 0
    outputs = output_file.read_text().strip().split("\n")
    assert json.loads(outputs[0]) == 3  # 1 + 2
    assert json.loads(outputs[1]) == 7  # 3 + 4


# Serve tests
def test_serve(temp_module):
    # Create a fresh runner for the server thread
    server_runner = CliRunner()
    server_thread = threading.Thread(
        target=lambda: server_runner.invoke(
            serve,
            [temp_module, "--host", "127.0.0.1", "--port", "49732"],
        )
    )
    server_thread.daemon = True
    server_thread.start()

    # Poll for server availability
    start_time = time.time()
    while time.time() - start_time < 5:
        try:
            httpx.get("http://127.0.0.1:49732/openapi.json")
            break
        except httpx.ConnectError:
            time.sleep(0.1)
    else:
        raise TimeoutError("Server failed to start")

    try:
        response = httpx.post("http://127.0.0.1:49732/add", json={"a": 1, "b": 2})
        assert response.status_code == 200
        assert response.json() == 3
    finally:
        server_thread.join(timeout=1)

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
    if result.exit_code == 0:
        raise AssertionError(f"Command succeeded with: {result.output}")
    assert "Missing option '--a'" in result.output


def test_run_extra_args(runner, temp_module):
    result = runner.invoke(run, [temp_module, "add", "1", "2", "3", "4"])
    if result.exit_code == 0:
        raise AssertionError(f"Command succeeded with: {result.output}")
    assert "Got unexpected extra argument" in result.output


def test_run_invalid_function_name(runner, temp_module):
    result = runner.invoke(run, [temp_module, "sad"])
    if result.exit_code == 0:
        raise AssertionError(f"Command succeeded with: {result.output}")
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
    data = json.loads(output_file.read_text())
    assert data["status"] == "success"
    assert data["output"] == 3


def test_run_with_json_input(runner, temp_module, tmp_path):
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"message": "hello"}))
    result = runner.invoke(run, [temp_module, "echo", "--input", str(input_file)])
    if result.exit_code != 0:
        raise AssertionError(f"Command failed with: {result.output}")
    assert result.output.strip() == "hello"


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
    assert json.loads(outputs[0])["output"] == 6  # 1 + 2 + 3
    assert json.loads(outputs[1])["output"] == 7  # 3 + 4


def test_run_empty_input_file(runner, temp_module, tmp_path):
    input_file = tmp_path / "empty.json"
    input_file.write_text("")
    result = runner.invoke(run, [temp_module, "add", "--input", str(input_file)])
    if result.exit_code == 0:
        raise AssertionError(f"Command succeeded with: {result.output}")
    assert "Input file is empty" in result.output


def test_run_invalid_json_input(runner, temp_module, tmp_path):
    input_file = tmp_path / "invalid.json"
    input_file.write_text("{invalid json}")
    result = runner.invoke(run, [temp_module, "add", "--input", str(input_file)])
    if result.exit_code == 0:
        raise AssertionError(f"Command succeeded with: {result.output}")
    assert "Invalid JSON" in result.output


def test_run_input_with_args_error(runner, temp_module, tmp_path):
    input_file = tmp_path / "input.json"
    input_file.write_text('{"a": 1, "b": 2}')
    result = runner.invoke(
        run, [temp_module, "add", "--input", str(input_file), "--a", "1"]
    )
    if result.exit_code == 0:
        raise AssertionError(f"Command succeeded with: {result.output}")
    assert "Cannot specify function arguments when using --input" in result.output


def test_run_duplicate_argument(runner, temp_module):
    result = runner.invoke(
        run, [temp_module, "add", "--a", "1", "--a", "2", "--b", "3"]
    )
    if result.exit_code == 0:
        raise AssertionError(f"Command succeeded with: {result.output}")
    assert "Got multiple values for argument 'a'" in result.output


def test_run_missing_option_value(runner, temp_module):
    result = runner.invoke(run, [temp_module, "add", "--a"])
    if result.exit_code == 0:
        raise AssertionError(f"Command succeeded with: {result.output}")
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

    result = runner.invoke(run, [temp_module, "add", "--input", str(input_file)])
    if result.exit_code == 0:
        raise AssertionError(f"Command succeeded with: {result.output}")
    assert "validation error" in result.output


def test_run_with_metadata(runner, temp_module, tmp_path):
    """Test that output includes metadata when writing to a file."""
    output_file = tmp_path / "output.json"
    result = runner.invoke(
        run, [temp_module, "--output", str(output_file), "add", "1", "2"]
    )
    assert result.exit_code == 0

    with open(output_file, encoding="utf-8") as f:
        data = json.loads(f.read())

    # Check the shape of the output JSON
    assert isinstance(data, dict)
    assert data["status"] == "success"
    assert data["output"] == 3
    assert data["error"] is None
    assert "id" in data
    assert "started_at" in data
    assert "completed_at" in data
    assert data["started_at"] < data["completed_at"]


def test_batch_processing_with_failures(runner, temp_module, tmp_path):
    """Test batch processing with mixed successes and failures."""
    input_file = tmp_path / "input.jsonl"
    input_lines = [
        json.dumps(input)
        for input in [
            {"a": 1, "b": 2},
            {"a": "invalid", "b": 2},
            {"a": 3, "b": 4},
        ]
    ]
    input_file.write_text("\n".join(input_lines))
    output_file = tmp_path / "output.json"

    result = runner.invoke(
        run,
        [temp_module, "add", "--input", str(input_file), "--output", str(output_file)],
    )
    if result.exit_code != 0:
        raise AssertionError(f"Command failed with: {result.output}")

    with open(output_file, encoding="utf-8") as f:
        jobs = json.loads(f.read())

    assert isinstance(jobs, list)
    assert len(jobs) == 3

    # Check first result (success)
    assert jobs[0]["status"] == "success"
    assert jobs[0]["output"] == 3
    assert jobs[0]["error"] is None

    # Check second result (failure)
    assert jobs[1]["status"] == "failure"
    assert jobs[1]["output"] is None
    assert isinstance(jobs[1]["error"], dict)
    assert "validation error" in jobs[1]["error"]["message"]

    # Check third result (success)
    assert jobs[2]["status"] == "success"
    assert jobs[2]["output"] == 7
    assert jobs[2]["error"] is None


def test_batch_processing_jsonl(runner, temp_module, tmp_path):
    """Test batch processing with JSONL input and output."""
    input_file = tmp_path / "input.jsonl"
    input_lines = [
        json.dumps(input)
        for input in [
            {"a": 1, "b": 2},
            {"a": "invalid", "b": 2},
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

    with open(output_file, encoding="utf-8") as f:
        jobs = [json.loads(line) for line in f]

    # Check first result (success)
    assert jobs[0]["status"] == "success"
    assert jobs[0]["output"] == 3
    assert jobs[0]["error"] is None

    # Check second result (failure)
    assert jobs[1]["status"] == "failure"
    assert jobs[1]["output"] is None
    assert isinstance(jobs[1]["error"], dict)
    assert "validation error" in jobs[1]["error"]["message"]

    # Check third result (success)
    assert jobs[2]["status"] == "success"
    assert jobs[2]["output"] == 7
    assert jobs[2]["error"] is None


def test_stdout_format(runner, temp_module):
    """Test that stdout format includes execution metadata."""
    result = runner.invoke(run, [temp_module, "add", "1", "2"])
    assert result.exit_code == 0

    assert json.loads(result.output.strip()) == 3


def test_stdout_batch_format(runner, temp_module, tmp_path):
    """Test that stdout includes metadata for batch operations."""
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"a": 1, "b": 2}))

    result = runner.invoke(run, [temp_module, "add", "--input", str(input_file)])
    assert result.exit_code == 0

    assert json.loads(result.output.strip()) == 3


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

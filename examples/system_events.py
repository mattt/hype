"""
This example shows how to use Ollama and macOS System Events together.

`uv run examples/system_events.py`
"""

# /// script
# dependencies = [
#   "ollama",
#   "hype @ git+https://github.com/mattt/hype.git",
# ]
# ///

import datetime
import os
import subprocess
from textwrap import dedent

import ollama

import hype


def _run_apple_script(
    script: str, capture_output: bool = False
) -> subprocess.CompletedProcess:
    """
    Private helper method to run AppleScript using launchctl.

    :param script: The AppleScript to run.
    :param capture_output: Whether to capture the output of the script.
    :return: A CompletedProcess instance.
    """
    uid = os.getuid()
    cmd = ["launchctl", "asuser", str(uid), "/usr/bin/osascript", "-e", script]
    return subprocess.run(cmd, capture_output=capture_output, text=True, check=True)  # noqa: S603


# FIXME: Either llama3.1 or ollama doesn't seem to support multiple tool calls.
#        Or else, llama3.1 can't figure out that it should use `get_current_time`
#        to get the current time.
@hype.up
def get_current_time() -> float:
    """
    Get the current time as a POSIX timestamp.
    """

    return datetime.datetime.now().timestamp()


@hype.up
def add_reminder(
    title: str, notes: str | None = None, due_date: datetime.datetime | None = None
) -> None:
    """
    Add a new reminder to the Reminders app.

    :param title: The title of the reminder.
    :param notes: Optional notes for the reminder.
    :param due_date: Optional due date for the reminder, in ISO format.
    """

    print(f"title: {title}")
    print(f"notes: {notes}")
    print(f"due_date: {due_date}")

    apple_script = dedent(f"""
        tell application "Reminders"
            set newReminder to make new reminder with properties {{name:"{title}"}}
            {f'set body of newReminder to "{notes}"' if notes else ''}
            {f'set due date of newReminder to date "{due_date:%B %d, %Y at %I:%M:%S %p}"' if due_date else ''}
        end tell
    """).strip()

    _run_apple_script(apple_script)


if __name__ == "__main__":
    tools = hype.create_ollama_tools(
        [
            get_current_time,
            add_reminder,
        ],
    )

    response = ollama.chat(
        model="llama3.1",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant that can interract with macOS System Events.",
            },
            {
                "role": "user",
                "content": "Add a reminder to buy groceries",
            },
        ],
        tools=tools,
    )

    print(response)

    results = tools(response["message"]["tool_calls"])  # pylint: disable=unsubscriptable-object
    print(results)

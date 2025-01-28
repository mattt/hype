#!/usr/bin/env -S uv run --script

"""
This example shows how to do Retrieval Augmented Generation (RAG) with OpenAI,
using the `sqlite-vec` extension to store and query the embeddings
from a SQLite database.

Unfortunately, macOS disables SQLite extensions by default,
so you'll need to run the example using Docker
(we recommend using [OrbStack](https://orbstack.dev/)).

```
export OPENAI_API_KEY="..."

docker run --rm \
           --platform linux/amd64 \
           -v $(pwd):/app -w /app \
           -e OPENAI_API_KEY="$OPENAI_API_KEY" \
           ghcr.io/astral-sh/uv:bookworm uv run examples/rag.py
```
"""


# /// script
# dependencies = [
#   "openai",
#   "numpy",
#   "pydantic",
#   "sqlite-vec",
#   "hype @ git+https://github.com/mattt/hype.git",
# ]
# ///

import contextlib
import datetime
import sqlite3
import struct
from collections.abc import Generator

import sqlite_vec
from openai import OpenAI
from pydantic import BaseModel

import hype


class Journal:
    class Entry(BaseModel):
        date: datetime.date
        content: str

    _db: sqlite3.Connection
    _client: OpenAI

    def __init__(self, client: OpenAI) -> None:
        self._client = client

    def __enter__(self) -> "Journal":
        self._db = sqlite3.connect(":memory:")

        # Load the sqlite-vec extension
        self._db.enable_load_extension(True)
        sqlite_vec.load(self._db)
        self._db.enable_load_extension(False)

        # Register the date adapter and converter
        sqlite3.register_adapter(datetime.date, lambda d: d.isoformat())
        sqlite3.register_converter(
            "DATE", lambda s: datetime.datetime.strptime(s.decode(), "%Y-%m-%d").date()
        )

        # Create the entries table
        cursor = self._db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                content TEXT NOT NULL
            )
        """)

        # Create the vector table
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_entries USING vec0(
                id INTEGER PRIMARY KEY,
                embedding FLOAT[1536]
            )
        """)

        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._db.close()

    @contextlib.contextmanager
    def cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        cursor = self._db.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def add(self, entries: Entry | list[Entry]) -> None:
        entries = entries if isinstance(entries, list) else [entries]

        response = self._client.embeddings.create(
            input=[entry.content for entry in entries], model="text-embedding-3-small"
        )
        embeddings = [embedding.embedding for embedding in response.data]

        with self.cursor() as cursor:
            for entry, embedding in zip(entries, embeddings, strict=False):
                cursor.execute(
                    "INSERT INTO entries (date, content) VALUES (?, ?)",
                    (entry.date, entry.content),
                )
                entry_id = cursor.lastrowid

                cursor.execute(
                    "INSERT INTO vec_entries (id, embedding) VALUES (?, ?)",
                    (entry_id, _serialize(embedding)),
                )

        self._db.commit()  # Don't forget to commit the changes


def _serialize(vector: list[float]) -> bytes:
    """Serializes a list of floats into a compact "raw bytes" format"""
    return struct.pack(f"{len(vector)}f", *vector)


ENTRIES = {
    "1848-04-01": "Departed Independence. Spirits high, supplies plentiful.",
    "1848-04-15": "Crossed the Kansas River. Wagon nearly tipped. All safe.",
    "1848-05-03": "Buffalo sighted. Hunted for fresh meat. Oxen tired.",
    "1848-05-20": "Reached Fort Kearny. Traded for supplies. Rested two days.",
    "1848-06-08": "Chimney Rock in view. Landmark lifts morale. Water low.",
    "1848-06-25": "Steep hill ahead. Discarded 100 lbs of supplies to lighten load.",
    "1848-07-12": "Crossed the Green River. Lost one ox. Pace slowed.",
    "1848-07-30": "Soda Springs reached. Filled water barrels. Mended wagon wheel.",
    "1848-08-15": "Snake River crossing. Perilous but successful.",
    "1848-09-01": "Blue Mountains in sight. Food running low. Push on to Oregon.",
}


if __name__ == "__main__":
    client = OpenAI()

    with Journal(client) as db:
        print("Populating the database...")
        entries = [
            Journal.Entry(
                date=datetime.datetime.strptime(date, "%Y-%m-%d").date(),
                content=content,
            )
            for date, content in ENTRIES.items()
        ]
        db.add(entries)

        @hype.up
        def search(query: str, top_k: int) -> list[Journal.Entry]:
            """
            Search for journal entries that match the query.
            """

            response = client.embeddings.create(
                input=[query], model="text-embedding-3-small"
            )
            query_embedding = response.data[0].embedding

            with db.cursor() as cursor:
                results = cursor.execute(
                    """
                    SELECT
                        entries.date,
                        entries.content,
                        distance
                    FROM vec_entries
                    LEFT JOIN entries ON entries.id = vec_entries.id
                    WHERE embedding MATCH ?
                        AND k = ?
                    ORDER BY distance
                    """,
                    [_serialize(query_embedding), top_k],
                ).fetchall()

            return [
                Journal.Entry(date=date, content=content)
                for date, content, _ in results
            ]

        tools = hype.create_openai_tools([search])

        print("Chatting with the assistant...")
        assistant = client.beta.assistants.create(
            instructions="You are a helpful assistant. Use the provided tools to answer questions.",
            model="gpt-4o",
            tools=tools,
        )

        thread = client.beta.threads.create()
        message = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Based on the entries, when did we cross the Green River?",
        )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant.id,
        )

        # Define the list to store tool outputs
        if run.required_action and run.required_action.submit_tool_outputs:
            tool_outputs = tools(run.required_action.submit_tool_outputs.tool_calls)

            # Submit all tool outputs at once after collecting them in a list
            if tool_outputs:
                run = client.beta.threads.runs.submit_tool_outputs_and_poll(
                    thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs
                )
            else:
                print("No tool outputs to submit.")

        if run.status == "completed":
            messages = client.beta.threads.messages.list(thread_id=thread.id)
            print(messages)
        else:
            print(run.status)

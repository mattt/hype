"""
This example shows how to do Retrieval Augmented Generation (RAG) with OpenAI.

`uv run examples/rag.py`
"""

# /// script
# dependencies = [
#   "openai",
#   "numpy",
#   "pydantic",
#   "hype @ git+https://github.com/mattt/hype.git",
# ]
# ///

import datetime
import sqlite3
import tempfile
from typing import Any, cast

import numpy as np
from openai import OpenAI
from pydantic import BaseModel

import hype

client = OpenAI()


class JournalEntry(BaseModel):
    date: datetime.date
    content: str


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


def generate_embeddings(texts: list[str]) -> list[np.ndarray]:
    response = client.embeddings.create(model="text-embedding-ada-002", input=texts)
    return [np.array(data.embedding, dtype=np.float32) for data in response.data]


if __name__ == "__main__":
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".db") as temp_db:
        with sqlite3.connect(temp_db.name) as conn:
            sqlite3.register_adapter(datetime.date, lambda d: d.isoformat())
            sqlite3.register_converter(
                "DATE",
                lambda s: datetime.datetime.strptime(s.decode(), "%Y-%m-%d").date(),
            )

            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB NOT NULL
                )
            """)

        entries = [
            JournalEntry(date=cast(Any, date), content=content)
            for date, content in ENTRIES.items()
        ]
        print("Generating embeddings...")
        embeddings = generate_embeddings([entry.content for entry in entries])

        for entry, embedding in zip(entries, embeddings, strict=True):
            cursor.execute(
                """
                INSERT INTO entries (date, content, embedding)
                VALUES (?, ?, ?)
                """,
                (entry.date, entry.content, np.array(embedding).tobytes()),
            )

        @hype.up
        def search(query: str, top_k: int) -> list[JournalEntry]:
            """
            Search for journal entries that match the query.
            """

            print(f'Searching for entries matching "{query}"...')

            results = []

            query_embedding = generate_embeddings([query])[0]

            cursor = conn.cursor()
            cursor.execute("SELECT date, content, embedding FROM entries")
            for row in cursor.fetchall():
                date, content, embedding_bytes = row
                document_embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
                similarity = np.dot(
                    query_embedding,
                    document_embedding,
                ) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(document_embedding)
                )
                results.append((JournalEntry(date=date, content=content), similarity))

            return [
                entry
                for entry, _ in sorted(results, key=lambda x: x[1], reverse=True)[
                    :top_k
                ]
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
            try:
                run = client.beta.threads.runs.submit_tool_outputs_and_poll(
                    thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs
                )
            except Exception as e:
                print("Failed to submit tool outputs:", e)
        else:
            print("No tool outputs to submit.")

    if run.status == "completed":
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        print(messages)
    else:
        print(run.status)

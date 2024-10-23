import asyncio
from uuid import UUID, uuid4


class Tasks:
    _tasks: dict[UUID, asyncio.Task]

    def __init__(self) -> None:
        self._tasks = {}

    def defer(self, task: asyncio.Task) -> UUID:
        id = uuid4()
        self._tasks[id] = task
        task.add_done_callback(lambda t: self._tasks.pop(id))
        return id

    def cancel(self, id: UUID) -> None:
        task = self._tasks.get(id)
        if task:
            task.cancel()

    def get(self, id: UUID) -> asyncio.Task | None:
        return self._tasks.get(id)

    def is_empty(self) -> bool:
        return not self._tasks

    async def wait_until_empty(self) -> None:
        while self._tasks:
            await asyncio.wait(self._tasks.values())

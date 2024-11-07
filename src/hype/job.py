from datetime import datetime, timezone
from enum import Enum
from typing import Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field

Input = TypeVar("Input")
Output = TypeVar("Output")


class Status(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELED = "canceled"


class Error(BaseModel):
    message: str


class Job(BaseModel, Generic[Input, Output]):
    """
    A Job manages multiple attempts (Tasks) at processing the same input.
    It owns retry logic and attempt history.
    """

    id: UUID = Field(default_factory=uuid4)
    input: Input
    output: Output | None = None
    error: Error | None = None

    # Timing for the overall job
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    canceled_at: datetime | None = None

    @computed_field
    @property
    def status(self) -> Status:
        if self.canceled_at is not None:
            return Status.CANCELED
        if self.error is not None:
            return Status.FAILURE
        if self.completed_at is not None:
            return Status.SUCCESS
        return Status.PENDING


class Batch(BaseModel, Generic[Input, Output]):
    """A collection of jobs."""

    id: UUID = Field(default_factory=uuid4)
    jobs: list[Job[Input, Output]] = Field(default_factory=list)
    canceled_at: datetime | None = None

    @property
    def status(self) -> Status:
        """Derive batch status from jobs"""
        if self.canceled_at is not None:
            return Status.CANCELED
        if not self.jobs:
            return Status.PENDING

        # If any job is running, batch is running
        if any(job.status == Status.RUNNING for job in self.jobs):  # pylint: disable=not-an-iterable
            return Status.RUNNING

        # If all jobs are done (success/failure/canceled), determine final status
        if all(
            job.status in {Status.SUCCESS, Status.FAILURE, Status.CANCELED}
            for job in self.jobs  # pylint: disable=not-an-iterable
        ):
            return (
                Status.SUCCESS
                if all(job.status == Status.SUCCESS for job in self.jobs)  # pylint: disable=not-an-iterable
                else Status.FAILURE
            )

        return Status.PENDING

    @property
    def progress(self) -> dict[Status, int]:
        """Count jobs in each status"""
        return {
            status: sum(1 for job in self.jobs if job.status == status)  # pylint: disable=not-an-iterable
            for status in Status
        }

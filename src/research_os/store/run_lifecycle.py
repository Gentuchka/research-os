"""Canonical run and job lifecycle states."""

from __future__ import annotations

from enum import StrEnum


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"
    REVIEWING = "REVIEWING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"
    REVIEWING = "REVIEWING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


ACTIVE_RUN_STATUSES = {
    RunStatus.QUEUED.value,
    RunStatus.STARTING.value,
    RunStatus.RUNNING.value,
    RunStatus.WAITING_FOR_REVIEW.value,
    RunStatus.REVIEWING.value,
}

TERMINAL_RUN_STATUSES = {
    RunStatus.FINISHED.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
}

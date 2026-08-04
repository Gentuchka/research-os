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

LEGAL_RUN_TRANSITIONS: dict[str, set[str]] = {
    RunStatus.QUEUED.value: {
        RunStatus.STARTING.value,
        RunStatus.RUNNING.value,
        RunStatus.CANCELLED.value,
    },
    RunStatus.STARTING.value: {
        RunStatus.RUNNING.value,
        RunStatus.FAILED.value,
        RunStatus.CANCELLED.value,
    },
    RunStatus.RUNNING.value: {
        RunStatus.WAITING_FOR_REVIEW.value,
        RunStatus.FINISHED.value,
        RunStatus.FAILED.value,
        RunStatus.CANCELLED.value,
    },
    RunStatus.WAITING_FOR_REVIEW.value: {
        RunStatus.REVIEWING.value,
        RunStatus.FINISHED.value,
        RunStatus.FAILED.value,
        RunStatus.CANCELLED.value,
    },
    RunStatus.REVIEWING.value: {
        RunStatus.FINISHED.value,
        RunStatus.FAILED.value,
        RunStatus.CANCELLED.value,
    },
}

LEGAL_JOB_TRANSITIONS: dict[str, set[str]] = {
    JobStatus.QUEUED.value: {
        JobStatus.STARTING.value,
        JobStatus.CANCELLED.value,
    },
    JobStatus.STARTING.value: {
        JobStatus.RUNNING.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELLED.value,
    },
    JobStatus.RUNNING.value: {
        JobStatus.WAITING_FOR_REVIEW.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELLED.value,
    },
    JobStatus.WAITING_FOR_REVIEW.value: {
        JobStatus.REVIEWING.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELLED.value,
    },
    JobStatus.REVIEWING.value: {
        JobStatus.FINISHED.value,
        JobStatus.FAILED.value,
        JobStatus.WAITING_FOR_REVIEW.value,
        JobStatus.CANCELLED.value,
    },
}

ALLOWED_BUDGET_NAMES = frozenset({"attempt", "token", "time", "tool", "branch"})


def assert_legal_transition(
    current: str,
    target: str,
    legal_map: dict[str, set[str]],
    *,
    label: str,
) -> None:
    if current == target:
        return
    allowed = legal_map.get(current, set())
    if target not in allowed:
        raise ValueError(f"Illegal {label} transition {current} -> {target}")

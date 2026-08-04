"""Typed MCP request/response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolContext(BaseModel):
    role: str
    run_id: str
    node_scope: str | None = None


class ApplyTransactionResult(BaseModel):
    tx_id: str
    accepted: bool
    rejections: list[dict[str, str]] = Field(default_factory=list)
    affected_node_ids: list[str] = Field(default_factory=list)
    git_commit_sha: str | None = None
    projection_status: str | None = None


class ReviewReportResult(BaseModel):
    decision: str
    reason_codes: list[str] = Field(default_factory=list)
    accepted: bool = False
    accepted_claim_indices: list[int] = Field(default_factory=list)
    rejected_claim_indices: list[int] = Field(default_factory=list)


class DispatchWorkerResult(BaseModel):
    status: str
    node_id: str | None = None
    job_id: str | None = None
    worker_run_id: str | None = None
    reviewer_run_id: str | None = None
    report_id: str | None = None
    decision: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    model: dict[str, Any] | None = None
    reason: str | None = None


class ActivityResult(BaseModel):
    path: str
    content: str


class ConsumeBudgetResult(BaseModel):
    node_id: str
    budget_name: str
    remaining: float


class CancelRunResult(BaseModel):
    status: str
    run_id: str
    reason: str


class ComputeMetricsResult(BaseModel):
    recomputed: list[str] = Field(default_factory=list)


class GraphStatisticsResult(BaseModel):
    object_count: int = 0
    math_edge_count: int = 0
    provenance_edge_count: int = 0
    frontier_count: int = 0


class ReportDict(BaseModel):
    id: str
    report_type: str
    subject_node_id: str
    status: str
    run_id: str
    payload: dict[str, Any]
    created_at: str


class SubmitReportResult(BaseModel):
    id: str
    report_type: str
    subject_node_id: str
    status: str
    run_id: str
    payload: dict[str, Any]
    created_at: str


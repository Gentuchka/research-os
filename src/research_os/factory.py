"""Application service factory."""

from __future__ import annotations

from dataclasses import dataclass

from research_os.anti_slop.engine import AntiSlopEngine
from research_os.config import RuntimeConfig
from research_os.kernel.transaction_service import TransactionService
from research_os.metrics.engine import MetricsEngine
from research_os.projection.activity import ActivityProjector
from research_os.projection.vault import VaultProjector
from research_os.reports.intake import ReportIntake
from research_os.reviewer.service import ReviewerService
from research_os.scheduler.service import SchedulerService
from research_os.store.connection import connect
from research_os.store.repository import Repository


@dataclass
class AppServices:
    config: RuntimeConfig
    repo: Repository
    tx_service: TransactionService
    report_intake: ReportIntake
    reviewer: ReviewerService
    metrics: MetricsEngine
    scheduler: SchedulerService
    vault: VaultProjector
    activity: ActivityProjector


def build_app(config: RuntimeConfig) -> AppServices:
    conn = connect(config.db_path)
    repo = Repository(conn)
    vault = VaultProjector(repo, config.vault_dir)
    activity = ActivityProjector(repo, config.vault_dir, config.activity_config)
    tx_service = TransactionService(repo, config, vault)
    anti_slop = AntiSlopEngine(repo, config.anti_slop_config)
    metrics = MetricsEngine(repo, config.frontier_config)
    report_intake = ReportIntake(repo)
    reviewer = ReviewerService(repo, tx_service, anti_slop, metrics, vault, activity)
    scheduler = SchedulerService(repo, report_intake, reviewer, metrics, activity, config)
    return AppServices(
        config=config,
        repo=repo,
        tx_service=tx_service,
        report_intake=report_intake,
        reviewer=reviewer,
        metrics=metrics,
        scheduler=scheduler,
        vault=vault,
        activity=activity,
    )


def build_service(config: RuntimeConfig) -> TransactionService:
    return build_app(config).tx_service

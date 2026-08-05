"""Operator CLI entry point (``ros``), P5.3.

A thin wrapper over the same MCP tool layer used by agents. All commands run
as ``role=human`` and go through the identical `_bootstrap()`/`_ctx()`/
`_guard()` ACL path as an MCP client — there is no direct DB access here.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ulid import ULID

from research_os.analytics.weekly import WeeklyAnalytics
from research_os.backup.service import BackupService
from research_os.config import RuntimeConfig
from research_os.factory import build_app
from research_os.kernel.types import KernelError
from research_os.mcp_server import server as srv


def _run_id(prefix: str) -> str:
    return f"run_cli_{prefix}_{ULID()}"


def _cmd_pin(args: argparse.Namespace) -> int:
    result = srv.pin_node(
        role="human", run_id=_run_id("pin"), node_id=args.node_id, weight=args.weight
    )
    print(f"Pinned {result.node_id} with weight {result.weight}")
    return 0


def _cmd_freeze(args: argparse.Namespace) -> int:
    result = srv.freeze_node(
        role="human", run_id=_run_id("freeze"), node_id=args.node_id, reason=args.reason or ""
    )
    print(f"{result.node_id} -> {result.status}")
    return 0


def _cmd_unfreeze(args: argparse.Namespace) -> int:
    result = srv.unfreeze_node(
        role="human", run_id=_run_id("unfreeze"), node_id=args.node_id, reason=args.reason or ""
    )
    print(f"{result.node_id} -> {result.status}")
    return 0


def _cmd_dispatch_worker(args: argparse.Namespace) -> int:
    result = srv.dispatch_worker(
        role="human", run_id=_run_id("dispatch"), node_id=args.node or ""
    )
    print(f"status={result.status} node={result.node_id} decision={result.decision}")
    return 0


def _cmd_dispatch_thinker(args: argparse.Namespace) -> int:
    result = srv.dispatch_thinker(role="human", run_id=_run_id("dispatch"))
    print(f"status={result.status} decision={result.decision}")
    return 0


def _cmd_activity(args: argparse.Namespace) -> int:
    result = srv.get_activity(role="human", run_id=_run_id("activity"))
    print(result.content)
    return 0


def _cmd_resolve_report(args: argparse.Namespace) -> int:
    decision = "ACCEPT" if args.accept else "REJECT"
    result = srv.resolve_needs_human(
        role="human",
        run_id=_run_id("resolve"),
        report_id=args.report_id,
        decision=decision,
        note=args.note or "",
    )
    print(f"report={args.report_id} decision={result.decision}")
    return 0


def _cmd_backup(args: argparse.Namespace) -> int:
    app = build_app(RuntimeConfig.load())
    service = BackupService(app.repo, app.config)
    snapshot_dir = service.backup(Path(args.backup_dir))
    print(f"Backup written to {snapshot_dir}")
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    app = build_app(RuntimeConfig.load())
    service = BackupService(app.repo, app.config)
    restored = service.restore(Path(args.snapshot_dir), force=args.force)
    print(f"Restored database to {restored}")
    return 0


def _cmd_weekly_report(args: argparse.Namespace) -> int:
    app = build_app(RuntimeConfig.load())
    analytics = WeeklyAnalytics(app.repo, app.config.vault_dir)
    path = analytics.generate(days=args.days)
    print(f"Weekly report written to {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ros", description="Research OS operator CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    pin = sub.add_parser("pin", help="Human priority pin on a node")
    pin.add_argument("node_id")
    pin.add_argument("--weight", type=float, default=1.0)
    pin.set_defaults(func=_cmd_pin)

    freeze = sub.add_parser("freeze", help="Freeze a node (pause it)")
    freeze.add_argument("node_id")
    freeze.add_argument("--reason", default="")
    freeze.set_defaults(func=_cmd_freeze)

    unfreeze = sub.add_parser("unfreeze", help="Unfreeze a node (resume it)")
    unfreeze.add_argument("node_id")
    unfreeze.add_argument("--reason", default="")
    unfreeze.set_defaults(func=_cmd_unfreeze)

    dispatch = sub.add_parser("dispatch", help="Dispatch a worker or thinker run")
    dispatch_sub = dispatch.add_subparsers(dest="dispatch_target", required=True)
    worker = dispatch_sub.add_parser("worker")
    worker.add_argument("--node", dest="node", default=None)
    worker.set_defaults(func=_cmd_dispatch_worker)
    thinker = dispatch_sub.add_parser("thinker")
    thinker.set_defaults(func=_cmd_dispatch_thinker)

    activity = sub.add_parser("activity", help="Print the current agent activity dashboard")
    activity.set_defaults(func=_cmd_activity)

    resolve = sub.add_parser("resolve-report", help="Resolve a NEEDS_HUMAN report")
    resolve.add_argument("report_id")
    group = resolve.add_mutually_exclusive_group(required=True)
    group.add_argument("--accept", action="store_true")
    group.add_argument("--reject", action="store_true")
    resolve.add_argument("--note", default="")
    resolve.set_defaults(func=_cmd_resolve_report)

    backup = sub.add_parser("backup", help="Snapshot the canonical DB + vault manifest (P7.2)")
    backup.add_argument("backup_dir")
    backup.set_defaults(func=_cmd_backup)

    restore = sub.add_parser("restore", help="Restore the canonical DB from a backup snapshot")
    restore.add_argument("snapshot_dir")
    restore.add_argument("--force", action="store_true")
    restore.set_defaults(func=_cmd_restore)

    weekly = sub.add_parser("weekly-report", help="Regenerate vault/00_meta/WEEKLY.md (P7.3)")
    weekly.add_argument("--days", type=int, default=7)
    weekly.set_defaults(func=_cmd_weekly_report)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KernelError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (PermissionError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Long-running scheduler daemon (P7.1).

Polls the frontier on an interval, respects a global concurrency limit on
worker dispatches per poll, runs the Thinker on a configurable cadence, and
supports graceful shutdown via a stop event (wired to SIGINT/SIGTERM when
run as a script).
"""

from __future__ import annotations

import logging
import signal
import threading
from types import FrameType
from typing import Any

from research_os.config import RuntimeConfig
from research_os.factory import AppServices, build_app

logger = logging.getLogger(__name__)


class SchedulerDaemon:
    def __init__(
        self,
        app: AppServices,
        *,
        poll_interval_seconds: float = 30.0,
        max_concurrent_workers: int = 1,
        thinker_cadence: int = 10,
    ) -> None:
        self.app = app
        self.poll_interval_seconds = poll_interval_seconds
        self.max_concurrent_workers = max_concurrent_workers
        self.thinker_cadence = thinker_cadence
        self._stop = threading.Event()
        self._poll_count = 0

    def stop(self) -> None:
        self._stop.set()

    def run_once(self) -> dict[str, Any]:
        """Run a single poll cycle. Dispatches up to `max_concurrent_workers`
        worker runs from the current frontier, and a Thinker synthesis run
        every `thinker_cadence` polls. Returns a summary dict for logging/tests."""
        self._poll_count += 1
        worker_results: list[dict[str, Any]] = []
        for _ in range(max(1, self.max_concurrent_workers)):
            result = self.app.scheduler.dispatch_next()
            worker_results.append(result)
            if result.get("status") == "idle":
                break
        thinker_result = None
        if self._poll_count % max(1, self.thinker_cadence) == 0:
            thinker_result = self.app.scheduler.dispatch_thinker()
        return {
            "poll": self._poll_count,
            "worker_results": worker_results,
            "thinker_result": thinker_result,
        }

    def run_forever(self, *, max_iterations: int | None = None) -> int:
        """Run poll cycles until `stop()` is called (or `max_iterations` is
        reached, for tests/bounded runs). Returns the number of iterations run."""
        iterations = 0
        while not self._stop.is_set():
            summary = self.run_once()
            logger.info("scheduler daemon poll %s: %s", summary["poll"], summary)
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
            self._stop.wait(self.poll_interval_seconds)
        return iterations


def _install_signal_handlers(daemon: SchedulerDaemon) -> None:
    def _handler(signum: int, frame: FrameType | None) -> None:
        logger.info("received signal %s, shutting down scheduler daemon", signum)
        daemon.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError, AttributeError):
            # Not available on this platform/thread (e.g. non-main thread).
            pass


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    config = RuntimeConfig.load()
    app = build_app(config)
    daemon_config = config.activity_config.get("daemon", {}) if config.activity_config else {}
    daemon = SchedulerDaemon(
        app,
        poll_interval_seconds=float(daemon_config.get("poll_interval_seconds", 30.0)),
        max_concurrent_workers=int(daemon_config.get("max_concurrent_workers", 1)),
        thinker_cadence=int(daemon_config.get("thinker_cadence", 10)),
    )
    _install_signal_handlers(daemon)
    daemon.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

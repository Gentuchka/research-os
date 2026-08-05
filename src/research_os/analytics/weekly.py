"""Weekly research health analytics (P7.3).

Aggregates transactions, review decisions, and budget usage over a trailing
window into a human-readable `vault/00_meta/WEEKLY.md` report. Purely
descriptive statistics — no bearing on proof/counterexample acceptance,
which remains the Reviewer's call.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from research_os.store.repository import Repository


class WeeklyAnalytics:
    def __init__(self, repo: Repository, vault_dir: Path) -> None:
        self.repo = repo
        self.vault_dir = vault_dir

    def generate(self, *, days: int = 7, now: datetime | None = None) -> Path:
        now = now or datetime.now(UTC)
        since_iso = (now - timedelta(days=days)).isoformat()

        transactions = self.repo.list_transactions_since(since_iso)
        decisions = self.repo.list_review_decisions_since(since_iso)
        budget_usage = self.repo.list_run_budget_usage_since(since_iso)

        accepted_tx = [t for t in transactions if t["accepted"]]

        decision_counts: dict[str, int] = {}
        reason_code_counts: dict[str, int] = {}
        for decision in decisions:
            decision_counts[decision["decision"]] = decision_counts.get(decision["decision"], 0) + 1
            if decision["decision"] == "REJECT":
                for code in decision["reason_codes"]:
                    reason_code_counts[code] = reason_code_counts.get(code, 0) + 1
        total_decisions = len(decisions)
        reject_rate = decision_counts.get("REJECT", 0) / total_decisions if total_decisions else 0.0

        budget_by_name: dict[str, float] = {}
        runs_with_usage: set[str] = set()
        for row in budget_usage:
            budget_by_name[row["budget_name"]] = (
                budget_by_name.get(row["budget_name"], 0.0) + float(row["amount"])
            )
            runs_with_usage.add(row["run_id"])

        accepted_decisions = decision_counts.get("ACCEPT", 0) + decision_counts.get(
            "PARTIAL_ACCEPT", 0
        )
        velocity = accepted_decisions / len(runs_with_usage) if runs_with_usage else 0.0

        path = self.vault_dir / "00_meta" / "WEEKLY.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "---",
            "generated_by: WeeklyAnalytics.generate",
            f"window_days: {days}",
            "---",
            "",
            "# Weekly research health",
            "",
            f"_Window: last {days} days, ending {now.isoformat()}._",
            "",
            "## Transactions",
            f"- Accepted transactions: {len(accepted_tx)}",
            f"- Total transaction attempts: {len(transactions)}",
            "",
            "## Review decisions",
            f"- Total decisions: {total_decisions}",
            f"- Reject rate: {reject_rate:.1%}",
        ]
        for decision_kind, count in sorted(decision_counts.items()):
            lines.append(f"- {decision_kind}: {count}")
        lines.extend(["", "## Slop rejection breakdown by reason code"])
        if reason_code_counts:
            for code, count in sorted(reason_code_counts.items(), key=lambda kv: -kv[1]):
                lines.append(f"- {code}: {count}")
        else:
            lines.append("_No rejections in this window._")
        lines.extend(["", "## Budget burn"])
        if budget_by_name:
            for name, amount in sorted(budget_by_name.items()):
                lines.append(f"- {name}: {amount:.1f}")
        else:
            lines.append("_No budget usage recorded in this window._")
        lines.extend(
            [
                "",
                "## Research velocity",
                f"- Accepted decisions per run with budget usage: {velocity:.2f}",
                "",
            ]
        )
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

"""Git commit bridge for accepted transactions."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from research_os.kernel.types import Transaction


def commit_transaction(
    *,
    repo_root: Path,
    tx: Transaction,
    projected_paths: list[Path],
    transactions_dir: Path,
) -> str | None:
    transactions_dir.mkdir(parents=True, exist_ok=True)
    export_path = transactions_dir / f"{tx.id}.json"
    export_path.write_text(json.dumps(tx.to_dict(), indent=2), encoding="utf-8")

    paths = [export_path, *projected_paths]
    rel_paths = [str(path.relative_to(repo_root)) for path in paths if path.exists()]
    if not rel_paths:
        return None

    subprocess.run(["git", "add", *rel_paths], cwd=repo_root, check=True)
    message = f"ros(tx): {tx.id} {tx.summary}"
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return sha.stdout.strip()

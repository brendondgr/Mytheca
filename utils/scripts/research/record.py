"""Write-time capture of the reproducibility record.

Contract §7.2: on every evaluation run, git commit, config hash, data version,
seeds, environment, hardware, wall-clock and final metrics go straight into the
experiment's ``manifest.yaml`` and ``data/metrics.json``. The point is that the
pipeline writes the record — anything depending on human diligence afterwards does
not happen.

This module only *captures*. It never decides what a number means.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from . import REPO_ROOT


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def git_block(entrypoint: str) -> dict[str, Any]:
    return {
        "commit": _git("rev-parse", "HEAD") or "unknown",
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        "entrypoint": entrypoint,
        "dirty": bool(_git("status", "--porcelain")),
    }


def hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def hardware() -> str:
    """Best-effort description of what this ran on. Honest about being coarse — a
    wrong CPU model is worse than 'unknown'."""
    bits = [platform.machine(), platform.system()]
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    bits.append(line.split(":", 1)[1].strip())
                    break
    except OSError:
        pass
    try:
        import os

        cores = os.cpu_count()
        if cores:
            bits.append(f"{cores} cores")
    except Exception:  # pragma: no cover - informational only
        pass
    return " · ".join(b for b in bits if b)


@dataclass
class RunRecord:
    """Accumulates one experiment's captured state across all its runs."""

    entrypoint: str
    wall_clock_seconds: float = 0.0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    per_run: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add_run(self, row: dict[str, Any]) -> None:
        self.per_run.append(row)

    def note(self, message: str) -> None:
        """Anything that will need to appear in ISSUES.md. Recorded as it happens,
        because it will not be remembered afterwards."""
        self.notes.append(message)


def aggregate(rows: list[dict[str, Any]], keys: list[str]) -> dict[str, dict[str, Any]]:
    """Mean/std/n per metric across runs.

    ``std`` is the population standard deviation over the runs actually present. It is
    omitted for a single run rather than reported as 0.0, because 0.0 reads as
    "no variance observed" when the truth is "variance not measurable".
    """
    out: dict[str, dict[str, Any]] = {}
    for key in keys:
        values = [float(r[key]) for r in rows if r.get(key) is not None]
        if not values:
            continue
        n = len(values)
        mean = sum(values) / n
        cell: dict[str, Any] = {"mean": round(mean, 6), "n": n}
        if n > 1:
            variance = sum((v - mean) ** 2 for v in values) / n
            cell["std"] = round(variance**0.5, 6)
        out[key] = cell
    return out


def write_metrics(experiment_dir: Path, record: RunRecord, values: dict[str, Any]) -> None:
    data_dir = experiment_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    (data_dir / "metrics.json").write_text(
        json.dumps(
            {
                "aggregate": values,
                "per_run": record.per_run,
                "totals": {
                    "llm_calls": record.llm_calls,
                    "input_tokens": record.input_tokens,
                    "output_tokens": record.output_tokens,
                    "wall_clock_seconds": round(record.wall_clock_seconds, 3),
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # CSV carries the per-seed raw numbers, so a reader can recompute the aggregate
    # rather than trust it.
    if record.per_run:
        columns = sorted({k for row in record.per_run for k in row})
        lines = [",".join(columns)]
        for row in record.per_run:
            lines.append(",".join(str(row.get(c, "")) for c in columns))
        (data_dir / "metrics.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_manifest(experiment_dir: Path, updates: dict[str, Any]) -> None:
    """Merge captured state into the manifest, one level deep.

    Deliberately a merge and not a rewrite: fields a human wrote (purpose, hypothesis,
    the pre-registered protocol's metric name) must survive a run.
    """
    path = experiment_dir / "manifest.yaml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(manifest.get(key), dict):
            manifest[key] = {**manifest[key], **value}
        else:
            manifest[key] = value

    path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def write_environment(experiment_dir: Path, record: RunRecord) -> None:
    env_dir = experiment_dir / "env"
    env_dir.mkdir(parents=True, exist_ok=True)

    lock = REPO_ROOT / "uv.lock"
    if lock.exists():
        (env_dir / "requirements.lock").write_text(
            f"# Pointer to the authoritative lockfile — see the contract §7.6 for why\n"
            f"# large artifacts are referenced rather than copied.\n"
            f"uv.lock {hash_file(lock)}\n",
            encoding="utf-8",
        )

    (env_dir / "hardware.md").write_text(
        "# Hardware and environment\n\n"
        f"| Field | Value |\n| --- | --- |\n"
        f"| Hardware | {hardware()} |\n"
        f"| Python | {sys.version.split()[0]} |\n"
        f"| Platform | {platform.platform()} |\n"
        f"| Wall clock | {record.wall_clock_seconds:.1f} s |\n"
        f"| LLM calls | {record.llm_calls} |\n"
        f"| Input tokens | {record.input_tokens} |\n"
        f"| Output tokens | {record.output_tokens} |\n"
        f"| Estimated cost | $0.00 (local inference) |\n"
        f"| Date | {date.today().isoformat()} |\n",
        encoding="utf-8",
    )

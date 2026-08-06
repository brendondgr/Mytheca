"""Fixtures for the research-record tooling tests.

These tests must never touch the real ``docs/research/``. Every fixture points the
tooling's module-level path constants at a temporary tree, so a bug in the validator
cannot rewrite the actual record.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REAL_RESEARCH = REPO_ROOT / "docs" / "research"


@pytest.fixture
def research_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway docs/research/ with the real templates and a minimal CLAIMS.md."""
    root = tmp_path / "docs" / "research"
    (root / "experiments").mkdir(parents=True)
    shutil.copytree(REAL_RESEARCH / "templates", root / "templates")

    (root / "CLAIMS.md").write_text(
        "# Claims Ledger\n\n"
        "| ID | Claim | Status |\n|----|-------|--------|\n"
        "| C-001 | A test claim | unsupported |\n"
        "| C-005 | Another test claim | unsupported |\n",
        encoding="utf-8",
    )

    from utils.scripts.research import gen_index, new_experiment, validate_research

    for module in (gen_index, new_experiment, validate_research):
        monkeypatch.setattr(module, "RESEARCH_ROOT", root, raising=False)
        monkeypatch.setattr(module, "EXPERIMENTS_DIR", root / "experiments", raising=False)
        monkeypatch.setattr(module, "TEMPLATE_DIR", root / "templates" / "experiment", raising=False)
        monkeypatch.setattr(module, "INDEX_PATH", root / "INDEX.md", raising=False)
        monkeypatch.setattr(module, "CLAIMS_PATH", root / "CLAIMS.md", raising=False)
        monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=False)

    return root

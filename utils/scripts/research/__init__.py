"""Research-record tooling.

Scaffolding, validation, and index generation for ``docs/research/``. The contract
these enforce is ``docs/research/AGENT_INSTRUCTIONS.md``; this package is its
executable half.

Not part of the Mytheca application. Nothing under ``web/backend/app/`` imports it.
"""

from pathlib import Path

# Repository root, resolved from this file: utils/scripts/research/__init__.py
REPO_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = REPO_ROOT / "docs" / "research"
EXPERIMENTS_DIR = RESEARCH_ROOT / "experiments"
TEMPLATE_DIR = RESEARCH_ROOT / "templates" / "experiment"
INDEX_PATH = RESEARCH_ROOT / "INDEX.md"
CLAIMS_PATH = RESEARCH_ROOT / "CLAIMS.md"

__all__ = [
    "REPO_ROOT",
    "RESEARCH_ROOT",
    "EXPERIMENTS_DIR",
    "TEMPLATE_DIR",
    "INDEX_PATH",
    "CLAIMS_PATH",
]

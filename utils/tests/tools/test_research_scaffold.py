"""The scaffolder produces a valid, validator-passing experiment.

This is acceptance criterion #2 of the research-record contract §10.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from utils.scripts.research import new_experiment, validate_research


def test_scaffold_creates_the_full_contract_shape(research_tree: Path) -> None:
    target = new_experiment.scaffold("baseline-retrieval", today=date(2026, 8, 6))

    assert target.name == "EXP-2026-08-001-baseline-retrieval"
    for required in ("manifest.yaml", "PROTOCOL.md", "RESULTS.md", "ISSUES.md"):
        assert (target / required).exists(), f"{required} missing from scaffold"
    for sub in ("data", "env", "logs", "tables", "figures"):
        assert (target / sub).is_dir(), f"{sub}/ missing from scaffold"


def test_scaffold_prefills_id_slug_date_and_git_state(research_tree: Path) -> None:
    target = new_experiment.scaffold("baseline-retrieval", today=date(2026, 8, 6))
    manifest = yaml.safe_load((target / "manifest.yaml").read_text(encoding="utf-8"))

    assert manifest["id"] == "EXP-2026-08-001"
    assert manifest["slug"] == "baseline-retrieval"
    assert manifest["date_started"] == date(2026, 8, 6)
    assert manifest["status"] == "planned"

    # Captured mechanically, not guessed. `dirty` is a real value either way, so the
    # assertion is on type rather than on this checkout's incidental state.
    assert isinstance(manifest["code"]["dirty"], bool)
    assert manifest["code"]["commit"]
    assert manifest["code"]["branch"]


def test_scaffolded_experiment_passes_the_validator(research_tree: Path) -> None:
    """The whole point: `make new-experiment` must not produce something that
    immediately fails `make validate-research`."""
    target = new_experiment.scaffold("baseline-retrieval", today=date(2026, 8, 6))

    findings = validate_research.validate_all([target])

    assert findings.errors == []


def test_ids_increment_within_a_month(research_tree: Path) -> None:
    first = new_experiment.scaffold("alpha", today=date(2026, 8, 6))
    second = new_experiment.scaffold("beta", today=date(2026, 8, 9))

    assert first.name.startswith("EXP-2026-08-001")
    assert second.name.startswith("EXP-2026-08-002")


def test_id_sequence_restarts_each_month(research_tree: Path) -> None:
    new_experiment.scaffold("alpha", today=date(2026, 8, 6))
    september = new_experiment.scaffold("gamma", today=date(2026, 9, 1))

    assert september.name == "EXP-2026-09-001-gamma"


@pytest.mark.parametrize("bad_slug", ["Not_Kebab", "has spaces", "Trailing-", "UPPER"])
def test_scaffold_rejects_non_kebab_slugs(research_tree: Path, bad_slug: str) -> None:
    """The slug becomes part of a permanent directory name that is never renamed, so
    it is worth being strict about at creation time."""
    with pytest.raises(ValueError):
        new_experiment.scaffold(bad_slug)


def test_allocation_skips_ids_already_on_disk(research_tree: Path) -> None:
    """Ids are permanent handles used in figures, commit messages and drafts, so the
    allocator must never hand out one that exists — including one created by hand or
    by a merge that landed while this branch was open."""
    (research_tree / "experiments" / "EXP-2026-08-001-hand-made").mkdir()
    (research_tree / "experiments" / "EXP-2026-08-004-from-a-merge").mkdir()

    target = new_experiment.scaffold("alpha", today=date(2026, 8, 6))

    assert target.name == "EXP-2026-08-005-alpha"


def test_scaffold_refuses_to_overwrite_an_existing_folder(research_tree: Path) -> None:
    """Guard against a race between allocation and copy. Unreachable through normal
    use — which is the point; it should stay unreachable."""
    (research_tree / "experiments" / "EXP-2026-08-001-alpha").mkdir()

    with pytest.raises(FileExistsError):
        new_experiment.scaffold("alpha", today=date(2026, 8, 6), _force_id="EXP-2026-08-001")

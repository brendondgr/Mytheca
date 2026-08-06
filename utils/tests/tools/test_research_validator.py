"""The validator enforces the contract — and fails on deliberately broken folders.

Acceptance criterion #3 of the research-record contract §10 requires both halves:
passing on a good folder proves nothing on its own.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from utils.scripts.research import gen_index, new_experiment, validate_research


def _make(research_tree: Path, slug: str = "worked-example", **overrides) -> Path:
    """Scaffold, then promote to a complete experiment with real-looking metrics."""
    target = new_experiment.scaffold(slug, today=date(2026, 8, 6))
    manifest = yaml.safe_load((target / "manifest.yaml").read_text(encoding="utf-8"))
    manifest.update(
        {
            "status": "complete",
            "date_completed": date(2026, 8, 7),
            "seeds": [0, 1, 2],
            "n_runs": 3,
            "metrics": {
                "primary": "beats_per_turn",
                "values": {"beats_per_turn": {"mean": 4.2, "std": 0.3, "n": 3}},
            },
            "supports_claims": ["C-005"],
        }
    )
    manifest.update(overrides)
    _write(target, manifest)
    (target / "data" / "metrics.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    return target


def _write(target: Path, manifest: dict) -> None:
    (target / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def _errors(target: Path) -> list[str]:
    return validate_research.validate_all([target]).errors


# --- the good case -----------------------------------------------------------------


def test_a_well_formed_complete_experiment_passes(research_tree: Path) -> None:
    assert _errors(_make(research_tree)) == []


# --- §7.3 failure conditions, one test each -----------------------------------------


@pytest.mark.parametrize("missing", ["manifest.yaml", "PROTOCOL.md", "RESULTS.md"])
def test_missing_required_file_fails(research_tree: Path, missing: str) -> None:
    target = _make(research_tree)
    (target / missing).unlink()

    assert any(missing in e for e in _errors(target))


def test_manifest_failing_schema_validation_fails(research_tree: Path) -> None:
    target = _make(research_tree)
    manifest = yaml.safe_load((target / "manifest.yaml").read_text(encoding="utf-8"))
    del manifest["code"]  # the whole reproducibility block
    _write(target, manifest)

    assert any("manifest.code" in e for e in _errors(target))


def test_malformed_experiment_id_fails(research_tree: Path) -> None:
    target = _make(research_tree)
    manifest = yaml.safe_load((target / "manifest.yaml").read_text(encoding="utf-8"))
    manifest["id"] = "EXP-26-8-1"
    _write(target, manifest)

    assert _errors(target)


def test_complete_with_empty_metrics_fails(research_tree: Path) -> None:
    """The headline §7.3 rule: a finished experiment that recorded nothing."""
    target = _make(research_tree, metrics={"primary": None, "values": {}})

    errors = _errors(target)
    assert any("metrics.values is empty" in e for e in errors)


def test_primary_metric_absent_from_values_fails(research_tree: Path) -> None:
    target = _make(
        research_tree,
        metrics={
            "primary": "recall_at_10",
            "values": {"beats_per_turn": {"mean": 4.2, "std": 0.3, "n": 3}},
        },
    )

    assert any("metrics.primary" in e for e in _errors(target))


def test_multi_run_metric_without_std_fails(research_tree: Path) -> None:
    """Mean +/- std across seeds, never a bare mean."""
    target = _make(
        research_tree,
        metrics={
            "primary": "beats_per_turn",
            "values": {"beats_per_turn": {"mean": 4.2, "n": 3}},
        },
    )

    assert any("no std" in e for e in _errors(target))


def test_single_run_metric_may_omit_std(research_tree: Path) -> None:
    """A single run has no spread to report — the rule must not fire here."""
    target = _make(
        research_tree,
        seeds=[0],
        n_runs=1,
        metrics={
            "primary": "beats_per_turn",
            "values": {"beats_per_turn": {"mean": 4.2, "n": 1}},
        },
    )

    assert not any("no std" in e for e in _errors(target))


def test_figure_listed_but_absent_fails(research_tree: Path) -> None:
    target = _make(research_tree, figures=["fig-turn-structure"])

    assert any("no figures/fig-turn-structure" in e for e in _errors(target))


def test_figure_present_but_unlisted_fails(research_tree: Path) -> None:
    target = _make(research_tree)
    (target / "figures" / "fig-orphan.svg").write_text("<svg/>", encoding="utf-8")
    (target / "figures" / "make_figures.py").write_text("# generator\n", encoding="utf-8")

    assert any("not listed in the manifest" in e for e in _errors(target))


def test_figure_without_a_generating_script_fails(research_tree: Path) -> None:
    """§4: a figure nobody can regenerate is a figure that rots."""
    target = _make(research_tree, figures=["fig-turn-structure"])
    (target / "figures" / "fig-turn-structure.svg").write_text("<svg/>", encoding="utf-8")
    (target / "figures" / "fig-turn-structure.pdf").write_bytes(b"%PDF-1.4\n")

    assert any("no generating script" in e for e in _errors(target))


def test_figure_with_a_generating_script_passes(research_tree: Path) -> None:
    target = _make(research_tree, figures=["fig-turn-structure"])
    (target / "figures" / "fig-turn-structure.svg").write_text("<svg/>", encoding="utf-8")
    (target / "figures" / "fig-turn-structure.pdf").write_bytes(b"%PDF-1.4\n")
    (target / "figures" / "make_figures.py").write_text("# generator\n", encoding="utf-8")

    assert _errors(target) == []


def test_pointer_without_a_hash_fails(research_tree: Path) -> None:
    target = _make(research_tree)
    (target / "data" / "POINTERS.md").write_text(
        "# Pointers\n\n- results/runs/2026-08-06/transcripts.jsonl\n", encoding="utf-8"
    )

    assert any("no hash" in e for e in _errors(target))


def test_pointer_with_a_hash_passes(research_tree: Path) -> None:
    target = _make(research_tree)
    (target / "data" / "POINTERS.md").write_text(
        "# Pointers\n\n- results/runs/2026-08-06/transcripts.jsonl — "
        "sha256:0badc0ffee0123456789abcdef\n",
        encoding="utf-8",
    )

    assert _errors(target) == []


def test_unknown_claim_id_fails(research_tree: Path) -> None:
    """No orphan numbers: a claim referenced here must exist in CLAIMS.md."""
    target = _make(research_tree, supports_claims=["C-999"])

    assert any("C-999" in e and "CLAIMS.md" in e for e in _errors(target))


def test_folder_name_disagreeing_with_manifest_fails(research_tree: Path) -> None:
    target = _make(research_tree)
    manifest = yaml.safe_load((target / "manifest.yaml").read_text(encoding="utf-8"))
    manifest["slug"] = "something-else"
    _write(target, manifest)

    assert any("folder name" in e for e in _errors(target))


def test_superseded_without_a_successor_fails(research_tree: Path) -> None:
    target = _make(research_tree, status="superseded")

    assert any("superseded_by" in e for e in _errors(target))


# --- §3.4: failures stay on record --------------------------------------------------


def test_failed_experiment_with_no_metrics_is_allowed(research_tree: Path) -> None:
    """A crashed run must be recordable. Forcing it to invent numbers to satisfy the
    validator would defeat the entire purpose of keeping it."""
    target = _make(
        research_tree,
        status="failed",
        date_completed=date(2026, 8, 7),
        metrics={"primary": None, "values": {}},
        supports_claims=["C-005"],
    )

    assert _errors(target) == []


def test_planned_experiment_with_no_metrics_is_allowed(research_tree: Path) -> None:
    """Pre-registration happens before there is anything to measure."""
    target = new_experiment.scaffold("pre-registered", today=date(2026, 8, 6))

    assert _errors(target) == []


def test_failed_experiment_still_needs_a_completion_date(research_tree: Path) -> None:
    target = _make(
        research_tree,
        status="failed",
        date_completed=None,
        metrics={"primary": None, "values": {}},
    )

    assert any("date_completed" in e for e in _errors(target))


# --- INDEX.md ------------------------------------------------------------------------


def test_index_generation_is_idempotent(research_tree: Path) -> None:
    _make(research_tree)

    first = gen_index.render_index()
    second = gen_index.render_index()

    assert first == second


def test_index_lists_the_experiment_with_its_metric(research_tree: Path) -> None:
    _make(research_tree)

    body = gen_index.render_index()

    assert "EXP-2026-08-001" in body
    assert "beats_per_turn = 4.2 ± 0.3 (n=3)" in body
    assert "C-005" in body


def test_empty_index_says_so_honestly(research_tree: Path) -> None:
    body = gen_index.render_index()

    assert "No experiments recorded yet" in body


def test_stale_index_fails_the_full_validation(research_tree: Path) -> None:
    _make(research_tree)
    (research_tree / "INDEX.md").write_text("# Experiment Index\n\nstale\n", encoding="utf-8")

    errors = validate_research.validate_all().errors

    assert any("stale" in e for e in errors)


def test_regenerating_the_index_clears_the_staleness_error(research_tree: Path) -> None:
    _make(research_tree)
    (research_tree / "INDEX.md").write_text(
        gen_index.render_index(), encoding="utf-8"
    )

    errors = validate_research.validate_all().errors

    assert not any("stale" in e for e in errors)

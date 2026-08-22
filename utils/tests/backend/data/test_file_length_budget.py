"""No Python module under `web/backend/app/` may exceed 800 lines.

The repo rule is explicit: *"If your work grows a file past that, the plan must include the
split as its own phase."* A rule nothing enforces is a rule that holds until the first busy
afternoon — `turn_engine.py` reached 1,986 lines before anyone split it, and by then the split
was a day's work rather than an hour's.

This is the guard the split itself does not provide. It fails on the *next* file to cross the
line, while the fix is still small, and it names the offender rather than leaving someone to
find it.

It deliberately measures **every** module, not just the turn loop: the turn engine was not
special, it was just the one that grew fastest.
"""

from __future__ import annotations

from pathlib import Path

#: The repo's hard ceiling (`docs/skills/global-project-rules/SKILL.md`). Aim well under it.
MAX_LINES = 800

#: Where a file is long enough to be worth naming in the failure message.
WARN_LINES = 600

APP = Path(__file__).resolve().parents[4] / "web" / "backend" / "app"


def _modules() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if "__pycache__" not in p.parts)


def test_the_app_directory_is_actually_where_this_thinks_it_is():
    """A path guard, so a moved test cannot silently pass by measuring nothing."""
    mods = _modules()
    assert APP.is_dir(), f"{APP} is not a directory — the guard is measuring nothing"
    assert len(mods) > 50, f"only found {len(mods)} modules under {APP}"


def test_no_backend_module_exceeds_the_line_ceiling():
    over = [
        (p.relative_to(APP), len(p.read_text().splitlines()))
        for p in _modules()
        if len(p.read_text().splitlines()) > MAX_LINES
    ]
    assert not over, (
        "These modules are past the 800-line ceiling. Split them into their own phase "
        "rather than raising this number:\n"
        + "\n".join(f"  {name}: {n} lines" for name, n in sorted(over, key=lambda r: -r[1]))
    )


def test_report_the_modules_approaching_the_ceiling():
    """Not a failure — a visible list, so the next split is chosen deliberately rather than
    discovered when a file is already twice the limit."""
    close = sorted(
        (
            (p.relative_to(APP), len(p.read_text().splitlines()))
            for p in _modules()
            if WARN_LINES < len(p.read_text().splitlines()) <= MAX_LINES
        ),
        key=lambda r: -r[1],
    )
    for name, n in close:
        print(f"approaching the ceiling: {name} — {n} lines")
    assert True

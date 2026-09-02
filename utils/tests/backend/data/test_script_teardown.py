"""Any script that builds a throwaway world must also tear it down.

Every smoke harness and research runner here creates a real storyline against a real
backend. Without a teardown each run leaves one behind, and they accumulate in the author's
library one per run until somebody deletes them by hand — which is exactly what happened:
three runners shipped without one, and a fourth was deliberately given the opposite default
so a recorded experiment could be re-read (the fix there was to archive the run to a file,
which is where a record belongs, rather than to leave scaffolding in a database).

A guard rather than a convention, for the same reason `test_file_length_budget.py` is one:
the rule held until the first busy afternoon, and the failure is invisible — the run
succeeds, the numbers are right, and the mess is somewhere nobody is looking.

It is deliberately a **text** check. Importing these modules would require the backend
package, a configured endpoint and in some cases a live model; grepping their source costs
nothing and catches the thing that actually goes wrong, which is a missing call rather than
a subtly wrong one.
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[4] / "utils" / "scripts"

#: Creating a storyline: a POST to the collection, in any of the shapes these scripts use.
_CREATES = re.compile(r"""(post\(\s*f?["']/storylines["']|["']POST["']\s*,\s*f?["']/storylines["'])""")

#: Tearing one down: a DELETE, or a call to the shared helper.
_DELETES = re.compile(
    r"""(delete\(\s*f?["']/storylines/|["']DELETE["']\s*,\s*f?["']/storylines/|delete_world\()"""
)


def _scripts() -> list[Path]:
    return sorted(
        p
        for p in SCRIPTS.rglob("*.py")
        if "__pycache__" not in p.parts and p.name != "__init__.py"
    )


def test_the_scripts_directory_is_where_this_thinks_it_is():
    """A path guard, so a moved test cannot silently pass by scanning nothing."""
    found = _scripts()
    assert SCRIPTS.is_dir(), f"{SCRIPTS} is not a directory — the guard is scanning nothing"
    assert len(found) > 10, f"only found {len(found)} scripts under {SCRIPTS}"


def test_every_script_that_creates_a_storyline_also_deletes_one():
    offenders = []
    for path in _scripts():
        source = path.read_text()
        if _CREATES.search(source) and not _DELETES.search(source):
            offenders.append(path.name)
    assert not offenders, (
        "these scripts build a throwaway storyline and never delete it, so every run leaves "
        f"one in the library: {', '.join(offenders)}. Add a teardown in a `finally` — "
        "`run_conversation_scaling.delete_world` is the shared helper, and it never raises, "
        "because cleanup must not mask a run's result."
    )

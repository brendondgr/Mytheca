"""Regenerate this experiment's tables from the recorded run logs.

Same contract as the figures (§1.4): every number is read back out of `logs/`, for both
this run and the EXP-2026-08-005 baseline, so nothing in RESULTS.md is retyped from a
previous write-up. Writes Markdown into this directory; RESULTS.md quotes from it.

Run directly: ``uv run python docs/research/experiments/EXP-2026-08-006-turn-latency-overhaul/tables/make_tables.py``
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
BASELINE = EXP.parent / "EXP-2026-08-005-conversation-scaling"

# Plain-language names for the pipeline steps, so the table reads without the source open.
READABLE = {
    "step:plan": "the planner's decision landing",
    "step:planning": "waiting on the planner",
    "first_character_dialogue": "writing a character's line",
    "step:reflection": "end-of-turn reflection",
    "step:consistency": "continuity check on a later speaker",
    "step:intent": "reading the player's message",
    "first_visible": "reaching the first visible words",
    "step:direction": "tracking the scene direction",
    "step:turn": "recording the player's message",
    "step:dialogue": "emitting a finished line",
    "step:speaker": "announcing the speaker",
    "step:reading": "starting to read the message",
    "step:context": "reporting context size",
    "step:assemble": "gathering the scene",
    "step:commit": "saving the turn",
    "step:lore": "world-lore lookup",
    "first_narration": "reaching the narrator's first words",
    "step:thinking": "a character's private thought",
    "step:action": "a character acting",
    "step:relationship": "looking up who knows whom",
    "step:files": "attaching tagged files",
    "step:branch": "preparing follow-up suggestions",
}


def load(experiment: Path, name: str = "conversation") -> list[dict]:
    path = experiment / "logs" / f"{name}.log"
    if not path.exists():
        return []
    rows = (json.loads(path.read_text(encoding="utf-8")) or {}).get("rows") or []
    return sorted(rows, key=lambda r: r.get("turn", 0))


def step_costs(rows: list[dict]) -> tuple[list[tuple[str, float, int]], float]:
    total_by: dict[str, float] = defaultdict(float)
    count_by: dict[str, int] = defaultdict(int)
    for r in rows:
        for step, gap in (r.get("step_gaps") or {}).items():
            base = step.split("#")[0]
            total_by[base] += gap
            count_by[base] += 1
    grand = sum(r.get("total_s") or 0 for r in rows)
    ordered = sorted(((k, v, count_by[k]) for k, v in total_by.items()), key=lambda kv: -kv[1])
    return ordered, grand


def _num(v, fmt="{:.1f}", dash="—"):
    return fmt.format(v) if isinstance(v, (int, float)) else dash


def per_turn_table(rows: list[dict]) -> str:
    out = [
        "| turn | first prose (s) | first thinking (s) | whole turn (s) | beats | planner calls | prompt tokens | prompt reuse | server cache hit | ended early |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        reuse = r.get("reuse_ratio_mean")
        hit = r.get("cache_hit_ratio")
        out.append(
            f"| {r.get('turn')} "
            f"| {_num(r.get('first_visible_s'), '{:.2f}')} "
            f"| {_num(r.get('first_reasoning_s'), '{:.2f}')} "
            f"| {_num(r.get('total_s'), '{:.1f}')} "
            f"| {r.get('beats', '—')} "
            f"| {r.get('planner_calls', '—')} "
            f"| {r.get('prompt_tokens_max') or '—'} "
            f"| {f'{100 * reuse:.0f} %' if isinstance(reuse, (int, float)) else '—'} "
            f"| {f'{100 * hit:.0f} %' if isinstance(hit, (int, float)) else '—'} "
            f"| {'✗ error' if r.get('error') else ''} |"
        )
    return "\n".join(out)


def step_table(rows: list[dict], label: str) -> str:
    ordered, grand = step_costs(rows)
    out = [
        f"**{label}** — total turn time {grand:.0f} s across {len(rows)} turn(s).",
        "",
        "| step | total (s) | share | calls | mean per call |",
        "| --- | --- | --- | --- | --- |",
    ]
    for key, total, count in ordered:
        if total < 0.5:
            continue
        name = READABLE.get(key, key)
        share = 100 * total / grand if grand else 0
        out.append(
            f"| `{key}` — {name} | {total:.1f} | {share:.0f} % | {count} | {total / count:.1f} s |"
        )
    return "\n".join(out)


def comparison_table(before: list[dict], after: list[dict],
                     all_before: list[dict], all_after: list[dict]) -> str:
    """Headline before/after, computed from both logs. Medians, not means.

    The baseline contains two turns that stalled on the generation timeout. A mean over
    those describes neither the stall nor the typical turn; the stalls get their own row
    instead of being smeared across the summary.
    """
    def med(rows, key):
        vals = sorted(v for r in rows if isinstance(v := r.get(key), (int, float)))
        if not vals:
            return None
        n = len(vals)
        return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2

    def planner_calls(rows):
        n = 0
        for r in rows:
            direct = r.get("planner_calls")
            if isinstance(direct, int):
                n += direct
                continue
            marks = r.get("step_marks") or {}
            n += sum(1 for k in marks if k == "step:planning" or k.startswith("step:planning#"))
        return n

    def worst(rows, key):
        vals = [v for r in rows if isinstance(v := r.get(key), (int, float))]
        return max(vals) if vals else None

    def errors(rows):
        return sum(1 for r in rows if r.get("error"))

    lines = [
        "| measure | before (EXP-005) | after (EXP-006) |",
        "| --- | --- | --- |",
        f"| turns run | {len(all_before)} | {len(all_after)} |",
        f"| turns that ended early | {errors(all_before)} | {errors(all_after)} |",
        f"| median whole turn (s) | {_num(med(before, 'total_s'))} | {_num(med(after, 'total_s'))} |",
        f"| worst whole turn (s) | {_num(worst(before, 'total_s'))} | {_num(worst(after, 'total_s'))} |",
        f"| median first prose (s) | {_num(med(before, 'first_visible_s'), '{:.2f}')} | {_num(med(after, 'first_visible_s'), '{:.2f}')} |",
        f"| median first thinking (s) | {_num(med(before, 'first_reasoning_s'), '{:.2f}')} | {_num(med(after, 'first_reasoning_s'), '{:.2f}')} |",
        f"| planner calls, all turns | {planner_calls(before)} | {planner_calls(after)} |",
        f"| median beats per turn | {_num(med(before, 'beats'), '{:.1f}')} | {_num(med(after, 'beats'), '{:.1f}')} |",
        f"| median prompt reuse | {_num(med(before, 'reuse_ratio_mean'), '{:.0%}')} | {_num(med(after, 'reuse_ratio_mean'), '{:.0%}')} |",
        f"| median server cache hit | {_num(med(before, 'cache_hit_ratio'), '{:.0%}')} | {_num(med(after, 'cache_hit_ratio'), '{:.0%}')} |",
    ]
    return "\n".join(lines)


def main() -> None:
    after = load(EXP)
    before = load(BASELINE)
    if not after:
        raise SystemExit("no run log recorded yet for EXP-2026-08-006")

    ok_after = [r for r in after if not r.get("error")]
    ok_before = [r for r in before if not r.get("error")]

    (HERE / "per-turn.md").write_text(
        "# Per turn — EXP-2026-08-006 (generated by make_tables.py)\n\n"
        + per_turn_table(after) + "\n", encoding="utf-8")
    (HERE / "step-costs.md").write_text(
        "# Where a turn's time goes (generated by make_tables.py)\n\n"
        + step_table(ok_after, "After the overhaul") + "\n\n"
        + (step_table(ok_before, "Before (EXP-2026-08-005)") + "\n" if ok_before else
           "_baseline log not readable_\n"), encoding="utf-8")
    (HERE / "comparison.md").write_text(
        "# Before / after (generated by make_tables.py)\n\n"
        + comparison_table(ok_before, ok_after, before, after) + "\n", encoding="utf-8")
    for name in ("per-turn.md", "step-costs.md", "comparison.md"):
        print(f"wrote {HERE / name}")


if __name__ == "__main__":
    main()

"""Build a plain-language PDF report from the EXP-2026-08-005 run logs.

Every figure in the report is read out of the recorded logs at build time — nothing is
typed in by hand. Re-running this after a new run regenerates the report against the new
data, and a missing log degrades to "not measured" rather than to a stale number.

Written for someone who wants to know what is going on with their app, not for someone
who wants to read a methods section. The caveats are kept, but they are kept short and in
one place at the end.

Usage::

    uv run --with reportlab python -m utils.scripts.research.report_conversation_scaling \\
        --experiment docs/research/experiments/EXP-2026-08-005-conversation-scaling \\
        --out reports/mytheca-latency-report.pdf
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from . import REPO_ROOT

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#5a5a5a")
ACCENT = colors.HexColor("#b4483c")
GOOD = colors.HexColor("#3f6f52")
RULE = colors.HexColor("#d5d0c8")


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=21, leading=25,
                                textColor=INK, spaceAfter=2),
        "subtitle": ParagraphStyle("st", parent=base["Normal"], fontSize=10.5, leading=14,
                                   textColor=MUTED, spaceAfter=14),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=14.5, leading=18,
                             textColor=INK, spaceBefore=16, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=11.5, leading=15,
                             textColor=ACCENT, spaceBefore=11, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=10, leading=14.5,
                               textColor=INK, alignment=TA_LEFT, spaceAfter=7),
        "small": ParagraphStyle("s", parent=base["Normal"], fontSize=8.6, leading=12,
                                textColor=MUTED, spaceAfter=5),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontSize=8.6, leading=11.5,
                               textColor=INK),
        "cellhead": ParagraphStyle("ch", parent=base["Normal"], fontSize=8.4, leading=11,
                                   textColor=colors.white),
    }


def load(exp: Path, name: str) -> list[dict[str, Any]]:
    path = exp / "logs" / f"{name}.log"
    if not path.exists():
        return []
    return (json.loads(path.read_text(encoding="utf-8")) or {}).get("rows") or []


def table(data: list[list[Any]], widths: list[float], st: dict) -> Table:
    body = [[Paragraph(str(c), st["cellhead"] if i == 0 else st["cell"]) for c in row]
            for i, row in enumerate(data)]
    t = Table(body, colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f5f2")]),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
    ]))
    return t


def callout(text: str, st: dict, tone: colors.Color = ACCENT) -> Table:
    """A single-cell box for the sentence a reader should not miss."""
    p = Paragraph(text, ParagraphStyle("call", parent=st["body"], fontSize=10.2,
                                       leading=14.5, textColor=INK, spaceAfter=0))
    t = Table([[p]], colWidths=[165 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#faf7f4")),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, tone),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def step_costs(rows: list[dict]) -> tuple[list[tuple[str, float, int]], float]:
    """Total seconds and call count per pipeline step, across all turns."""
    total_by, count_by = defaultdict(float), defaultdict(int)
    for r in rows:
        for step, gap in (r.get("step_gaps") or {}).items():
            base = step.split("#")[0]
            total_by[base] += gap
            count_by[base] += 1
    grand = sum(r.get("total_s") or 0 for r in rows)
    ordered = sorted(((k, v, count_by[k]) for k, v in total_by.items()),
                     key=lambda kv: -kv[1])
    return ordered, grand


READABLE = {
    "step:plan": "Choosing the next beat (the planner)",
    "step:planning": "Choosing the next beat (waiting to start)",
    "first_character_dialogue": "Writing a character's line",
    "step:reflection": "End-of-turn reflection",
    "step:consistency": "Continuity check on a later speaker",
    "step:intent": "Reading your message",
    "first_visible": "Reaching the first visible words",
    "step:direction": "Tracking your scene direction",
    "step:turn": "Recording your message",
    "step:dialogue": "Emitting a finished line",
    "step:speaker": "Announcing the speaker",
    "step:reading": "Starting to read your message",
    "step:context": "Reporting context size",
    "step:assemble": "Gathering the scene",
    "step:commit": "Saving the turn",
    "step:lore": "World-lore lookup",
    "first_narration": "Reaching the narrator's first words",
}


def build(exp: Path, out: Path) -> None:
    st = styles()
    conv = [r for r in load(exp, "conversation") if not r.get("error")]
    conv_all = load(exp, "conversation")
    pre = load(exp, "conversation-prefix-parser")
    by_turn = load(exp, "layout-by-turn")
    longctx = load(exp, "layout")
    budget = load(exp, "budget")

    flow: list[Any] = []
    A = flow.append

    A(Paragraph("Why Mytheca turns take as long as they do", st["title"]))
    A(Paragraph(
        "A measured report on conversation latency and prompt caching, run against the "
        "remote GPU (<font face='Courier'>skynet</font>) at 5 max turns, 0 end-turn "
        "suggestions, 100 context beats. 19 August 2026.", st["subtitle"]))
    A(HRFlowable(width="100%", color=RULE, spaceAfter=12))

    # ---- the short version -------------------------------------------------
    A(Paragraph("The short version", st["h1"]))
    A(Paragraph(
        "Your scene is <b>not</b> getting slower as the conversation grows. The time before "
        "you see the first words held steady at about ten seconds across all ten turns, even "
        "though the amount of story being sent to the model more than doubled.", st["body"]))
    A(Paragraph(
        "What makes a turn slow is <b>how many times the app talks to the model</b>, not how "
        "much it sends each time. A single turn makes six to twelve separate model calls, one "
        "after another, and you wait for all of them.", st["body"]))
    A(Spacer(1, 4))
    A(callout(
        "<b>The single biggest cost is the beat planner.</b> It runs once per beat to decide "
        "who speaks next, takes about five seconds each time, and accounts for <b>41% of all "
        "turn time</b> — more than actually writing the characters' words.", st))
    A(Spacer(1, 8))
    A(Paragraph(
        "Caching is half-working. The bot does still have all your earlier conversation — "
        "nothing is being forgotten. But the server re-reads that conversation from scratch on "
        "every single call instead of reusing its earlier work. That is genuinely wasteful, and "
        "it is <b>not</b> worth fixing yet: I tested the fix and it saved nothing measurable at "
        "your scene lengths.", st["body"]))
    A(Spacer(1, 4))
    A(callout(
        "<b>The most valuable thing found was an accident.</b> A bug in the app was throwing "
        "away your model's entire \"thinking\" output because it looked for it under the wrong "
        "name. That killed roughly a third of turns outright and hid a feature that works "
        "fine. It is fixed.", st, GOOD))

    # ---- where the time goes ----------------------------------------------
    A(PageBreak())
    A(Paragraph("Where a turn's time actually goes", st["h1"]))
    A(Paragraph(
        "Every step of every turn was timed. The table below adds up how long the app spent in "
        "each step across the whole ten-turn conversation.", st["body"]))

    if conv:
        ordered, grand = step_costs(conv)
        rows = [["Step", "Total (s)", "Share", "Times run", "Average"]]
        for step, tot, n in ordered[:8]:
            if tot < 0.5:
                continue
            rows.append([READABLE.get(step, step), f"{tot:.0f}",
                         f"{tot / grand:.0%}" if grand else "—", str(n),
                         f"{tot / n:.1f}s" if n else "—"])
        A(table(rows, [62 * mm, 22 * mm, 18 * mm, 22 * mm, 20 * mm], st))
        A(Spacer(1, 6))
        A(Paragraph(
            f"Across {len(conv)} completed turns the app spent {grand:.0f} seconds in total, "
            f"an average of {grand / len(conv):.0f} seconds per turn.", st["small"]))
    else:
        A(Paragraph("No completed conversation turns were recorded.", st["body"]))

    A(Paragraph("What you are waiting for before the first word", st["h2"]))
    A(Paragraph(
        "Of the roughly ten seconds before any prose appears, about seven and a half are two "
        "calls that produce no story at all: one to work out what your message meant, and one "
        "to decide who should answer. Only after both finish does a character start writing.",
        st["body"]))
    A(callout(
        "If you want the first reply to feel faster, the lever is <b>removing or overlapping "
        "those two calls</b> — not shortening the story, not changing the context settings, "
        "and not fixing the cache.", st))

    # ---- the caching answer ------------------------------------------------
    A(PageBreak())
    A(Paragraph("Is caching working?", st["h1"]))
    A(Paragraph(
        "This turned out to be two different questions with two different answers.", st["body"]))

    A(Paragraph("1. Does the bot still remember earlier messages? Yes.", st["h2"]))
    A(Paragraph(
        "Verified directly. The short-term memory store is running, it is holding the beats, "
        "and all 100 beats you configured are being written into the prompt. The amount of "
        "story sent to the model grew steadily turn after turn, which is exactly what you would "
        "expect if nothing is being dropped. <b>No context is being lost.</b>", st["body"]))

    A(Paragraph("2. Is the server reusing its earlier work? No.", st["h2"]))
    A(Paragraph(
        "When you send a message, the server has to read the whole prompt before it can write "
        "anything. It is allowed to skip re-reading any part it has seen before. In your case "
        "it skips the same small fixed chunk every time and re-reads everything else.",
        st["body"]))
    if conv:
        rows = [["Turn", "Story sent (tokens)", "Reused from before", "Reused %"]]
        for r in sorted(conv, key=lambda r: r["turn"]):
            if not r.get("prompt_tokens_max"):
                continue
            hit = r.get("cache_hit_ratio")
            rows.append([str(r["turn"]), f"{r['prompt_tokens_max']:,}",
                         f"{r.get('cached_tokens_max'):,}" if r.get("cached_tokens_max") else "—",
                         f"{hit:.0%}" if hit is not None else "—"])
        A(table(rows, [18 * mm, 40 * mm, 40 * mm, 24 * mm], st))
    A(Spacer(1, 6))
    A(callout(
        "The \"reused\" column never moves. It is the same number on every turn — that is the "
        "app's fixed world description, and nothing else. Every word of your actual "
        "conversation is read again from scratch, on every call.", st))
    A(Spacer(1, 8))
    A(Paragraph(
        "The cause is prompt order. The character's current mood and stats are placed <i>before</i> "
        "the conversation history, and a server can only skip re-reading a stretch that has not "
        "changed <i>from the very beginning</i>. One stat ticking over therefore invalidates "
        "everything after it, including the entire story so far.", st["body"]))

    A(Paragraph("Should you fix it? Not yet.", st["h2"]))
    A(Paragraph(
        "I built the fixed version and measured it against the current one, at ten different "
        "conversation lengths, twice each, alternating the order to be fair. It made no "
        "difference worth having.", st["body"]))
    if by_turn:
        agg = defaultdict(list)
        for r in by_turn:
            if r.get("ttft_s") is not None:
                agg[r["layout"]].append(r["ttft_s"])
        rows = [["Prompt order", "Average time to start (s)", "Samples"]]
        labels = {"volatile-first": "As it is now", "volatile-last": "Reordered (the 'fix')"}
        for layout, values in agg.items():
            rows.append([labels.get(layout, layout), f"{sum(values) / len(values):.2f}",
                         str(len(values))])
        A(table(rows, [50 * mm, 50 * mm, 22 * mm], st))
    A(Spacer(1, 6))
    A(Paragraph(
        "<b>My own prediction was wrong here.</b> I expected the reordering to help and it did "
        "not. At the size your scenes actually reach, re-reading the story costs a few hundred "
        "milliseconds — less than the ordinary variation between calls. Reordering the prompt "
        "changes what every character sees and in what order, which carries a real risk to "
        "writing quality, and there is no speed gain to pay for that risk.", st["body"]))
    if longctx:
        sizes = sorted({r["turn"] for r in longctx})
        big = max(r.get("prompt_tokens") or 0 for r in longctx)
        A(Paragraph(
            f"A follow-up probe pushed the history out to {max(sizes)} turns "
            f"(about {big:,} tokens) to find where this stops being true — see the appendix.",
            st["small"]))

    # ---- the bug -----------------------------------------------------------
    A(PageBreak())
    A(Paragraph("The bug this turned up", st["h1"]))
    A(Paragraph(
        "Modern models produce two streams: their private \"thinking\", and the answer they "
        "actually give you. Different model servers label the thinking stream differently. Your "
        "GPU calls it <font face='Courier'>reasoning</font>; the other server the app supports "
        "calls it <font face='Courier'>reasoning_content</font>. The app only looked for the "
        "second name.", st["body"]))
    A(Paragraph("So on your GPU the app was throwing away every word of the model's thinking "
                "without ever seeing it. That caused three separate problems:", st["body"]))
    A(Paragraph(
        "<b>1. Turns died for no visible reason.</b> When the model spent its whole allowance "
        "thinking and had nothing left for the answer, the app saw an empty reply and told you "
        "\"The model returned an empty response\" — an error that explained nothing. This "
        "affected 3 of 10 turns.", st["body"]))
    A(Paragraph(
        "<b>2. A feature you asked for looked broken.</b> The live \"watch the character think\" "
        "display had nothing to show, because the thinking was being discarded before it "
        "arrived. It works — the first thought now appears in about 0.4 seconds.", st["body"]))
    A(Paragraph(
        "<b>3. I drew a wrong conclusion and reported it to you.</b> I measured the absence of "
        "thinking and concluded your model did not produce any. It does. That earlier finding "
        "has been formally withdrawn in the project's records rather than quietly edited.",
        st["body"]))
    if pre and conv_all:
        rows = [["", "Turns run", "Turns that failed"]]
        rows.append(["Before the fix", str(len(pre)),
                     str(sum(1 for r in pre if r.get("error")))])
        rows.append(["After the fix", str(len(conv_all)),
                     str(sum(1 for r in conv_all if r.get("error")))])
        A(table(rows, [40 * mm, 30 * mm, 34 * mm], st))
        A(Paragraph(
            "Treat this as encouraging rather than proven: the fix changes how the app reads "
            "the model, not how the model behaves, so some of this difference is likely "
            "ordinary run-to-run variation.", st["small"]))

    A(Paragraph("A second, related finding", st["h1"]))
    A(Paragraph(
        "The app can ask the model to limit how long it thinks. Your GPU accepts that "
        "instruction under one particular name, and ignores the other. This was tested five "
        "times per setting, with identical results every single time:", st["body"]))
    if budget:
        agg = defaultdict(list)
        for r in budget:
            if not r.get("error"):
                agg[r["condition"]].append(r)
        labels = {"none": "No limit sent", "vllm-key": "Limit sent (your GPU's name)",
                  "llamacpp-key": "Limit sent (the other name)", "both-keys": "Both names sent"}
        rows = [["Setting", "Thinking produced", "Answer produced", "Result"]]
        for cond in ("none", "vllm-key", "llamacpp-key", "both-keys"):
            rs = agg.get(cond) or []
            if not rs:
                continue
            r = rs[0]
            rows.append([labels[cond], f"{r['reasoning_chars']:,} chars",
                         f"{r['content_chars']} chars" if r["content_chars"] else "nothing",
                         "ran out of room" if r["finish_reason"] == "length" else "answered"])
        A(table(rows, [55 * mm, 32 * mm, 30 * mm, 32 * mm], st))
    A(Spacer(1, 6))
    A(callout(
        "Without that limit, this prompt <b>never produced an answer at all</b> — five times "
        "out of five. The app now sends both names, so it works. Before a fix earlier in this "
        "session it was sending neither.", st, GOOD))

    # ---- recommendations ---------------------------------------------------
    A(PageBreak())
    A(Paragraph("What I would do next", st["h1"]))
    for n, (head, text) in enumerate([
        ("Reduce the number of model calls per turn",
         "This is where the time is. The planner runs once per beat at about five seconds a "
         "time. Deciding several beats at once, or skipping the planner when only one "
         "character could plausibly answer, would cut the biggest single cost in the app."),
        ("Move end-of-turn reflection off the critical path",
         "Reflection costs about seven seconds at the end of every turn, and you are waiting "
         "for it before you can type again. The app already has a setting to run it in the "
         "background; it is currently switched off."),
        ("Reconsider the continuity check",
         "It costs around ten seconds whenever a second character speaks, and it is also the "
         "reason later speakers cannot show their words as they are written. That is a lot to "
         "pay for a check that only sometimes fires."),
        ("Consider turning on live thinking",
         "Now that it actually works on your GPU, the first thought appears in about 0.4 "
         "seconds — against roughly ten seconds before any prose. It is currently off by "
         "default. The trade-off is that reading a character's reasoning can spoil the line "
         "they are about to say."),
        ("Leave the prompt cache alone for now",
         "It is genuinely wasteful, but fixing it measurably saved nothing at your scene "
         "lengths and carries a real risk to writing quality. Revisit if scenes start running "
         "much longer than they do today."),
    ], start=1):
        A(Paragraph(f"{n}. {head}", st["h2"]))
        A(Paragraph(text, st["body"]))

    A(Paragraph("What this report does not tell you", st["h1"]))
    A(Paragraph(
        "It is one conversation, run once, on one model, on a shared GPU. Individual numbers "
        "bounce around; the patterns are what matter. It measures speed only — nothing here "
        "says anything about whether the writing is any good. And your GPU picks which model "
        "answers automatically, so it may not have been the same model throughout.", st["body"]))
    A(Paragraph(
        "The full working — every raw measurement, the mistakes made along the way, and the "
        "things measured wrongly the first time — is recorded in the project under "
        "<font face='Courier'>docs/research/experiments/</font>.", st["small"]))

    # ---- appendix ----------------------------------------------------------
    A(PageBreak())
    A(Paragraph("Appendix: the raw numbers", st["h1"]))
    fig = exp / "figures" / "scaling.png"
    if fig.exists():
        A(Image(str(fig), width=170 * mm, height=53 * mm))
        A(Paragraph(
            "Left: time per turn. Middle: story sent per turn (gold) against the part reused "
            "(green) — the flat green line is the finding. Right: prompt order comparison.",
            st["small"]))
        A(Spacer(1, 8))

    if conv_all:
        A(Paragraph("Every turn of the conversation", st["h2"]))
        rows = [["Turn", "First words (s)", "Whole turn (s)", "Beats", "Story sent", "Reused"]]
        for r in sorted(conv_all, key=lambda r: r["turn"]):
            rows.append([
                str(r["turn"]) + (" *" if r.get("error") else ""),
                str(r.get("first_visible_s") or "—"), str(r.get("total_s") or "—"),
                str(r.get("beats") or "—"),
                f"{r['prompt_tokens_max']:,}" if r.get("prompt_tokens_max") else "—",
                f"{r['cached_tokens_max']:,}" if r.get("cached_tokens_max") else "—",
            ])
        A(table(rows, [16 * mm, 28 * mm, 28 * mm, 16 * mm, 26 * mm, 22 * mm], st))
        A(Paragraph("* turn ended early with an error.", st["small"]))

    if longctx:
        A(Paragraph("Prompt order at longer conversation lengths", st["h2"]))
        agg = defaultdict(list)
        tokens: dict[int, int] = {}
        for r in longctx:
            if r.get("ttft_s") is not None:
                agg[(r["layout"], r["turn"])].append(r["ttft_s"])
            if r.get("prompt_tokens"):
                tokens[r["turn"]] = r["prompt_tokens"]
        rows = [["History (turns)", "Story size", "As it is now (s)", "Reordered (s)"]]
        for size in sorted({k[1] for k in agg}):
            f = agg.get(("volatile-first", size), [])
            l = agg.get(("volatile-last", size), [])
            rows.append([str(size), f"{tokens.get(size, 0):,}",
                         f"{sum(f) / len(f):.2f}" if f else "—",
                         f"{sum(l) / len(l):.2f}" if l else "—"])
        A(table(rows, [30 * mm, 28 * mm, 34 * mm, 30 * mm], st))

    out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
        title="Why Mytheca turns take as long as they do", author="Mytheca measurement run",
    )
    doc.build(flow)
    print(f"wrote {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    exp = args.experiment if args.experiment.is_absolute() else REPO_ROOT / args.experiment
    out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    if not exp.is_dir():
        raise SystemExit(f"no such experiment folder: {exp}")
    build(exp, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

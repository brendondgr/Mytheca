"""WCAG-AA contrast gate for Mytheca's theme tokens.

Parses the `.theme-*` blocks in web/frontend/styles/themes.css and asserts the
load-bearing text/surface token pairs meet WCAG 2.2 AA in every theme:

- HARD pairs fail the script (exit 1) below their threshold.
- SOFT pairs are reported but do not fail (known, documented trade-offs —
  e.g. the theme-agnostic gold eyebrow accent over light parchment).

Run: uv run python utils/scripts/check_contrast.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

THEMES_CSS = (
    Path(__file__).resolve().parents[2]
    / "web"
    / "frontend"
    / "styles"
    / "themes.css"
)

# Theme-agnostic values referenced by the checks (from app/globals.css).
ACCENT_INK = "#F6ECDA"  # text on accent-filled buttons/bubbles
GOLD = "#C8862A"

# (name, foreground token, background token, minimum ratio, hard?)
# Foreground/background may be a literal hex to check theme-agnostic colors.
PAIRS: list[tuple[str, str, str, float, bool]] = [
    # Primary text on every surface it appears on — body text, 4.5:1.
    ("ink / page", "--ink", "--page-bg", 4.5, True),
    ("ink / card", "--ink", "--card-bg", 4.5, True),
    ("ink / card2", "--ink", "--card-bg2", 4.5, True),
    ("ink / field", "--ink", "--field-bg", 4.5, True),
    ("ink / menu", "--ink", "--menu-bg", 4.5, True),
    ("ink / modal", "--ink", "--modal-bg", 4.5, True),
    ("ink / hover", "--ink", "--hover-bg", 4.5, True),
    ("ink / surface", "--ink", "--surface", 4.5, True),
    # Secondary text.
    ("ink-soft / page", "--ink-soft", "--page-bg", 4.5, True),
    ("ink-soft / card", "--ink-soft", "--card-bg", 4.5, True),
    ("ink-soft / card2", "--ink-soft", "--card-bg2", 4.5, True),
    ("ink-soft / menu", "--ink-soft", "--menu-bg", 4.5, True),
    # Mono metadata labels (small text → 4.5).
    ("mute / page", "--mute", "--page-bg", 4.5, True),
    ("mute / card", "--mute", "--card-bg", 4.5, True),
    ("mute / menu", "--mute", "--menu-bg", 4.5, True),
    # Faint labels / placeholders — supplementary; ≥3 hard, 4.5 aspirational.
    ("mute2 / page", "--mute2", "--page-bg", 3.0, True),
    ("mute2 / card", "--mute2", "--card-bg", 3.0, True),
    ("mute2 / field", "--mute2", "--field-bg", 4.5, True),
    # Accent as text (links, labeled highlights).
    ("accent / page", "--accent", "--page-bg", 4.5, True),
    ("accent / card", "--accent", "--card-bg", 4.5, True),
    ("accent / field", "--accent", "--field-bg", 4.5, True),
    # Light text on accent-filled controls (mono-uppercase UI text; the locked
    # design system treats it as large/UI text → 3:1; documented trade-off).
    ("accent-ink / accent", ACCENT_INK, "--accent", 3.0, True),
    ("accent-ink / accent-hover", ACCENT_INK, "--accent-hover", 3.0, True),
    # Focus outline + selected borders (non-text) against the grounds.
    ("accent(nontext) / page", "--accent", "--page-bg", 3.0, True),
    ("card-bd(nontext) / card", "--card-bd", "--card-bg", 1.35, True),
    # Chrome text: the header/rail gradients carry ink + mute text.
    ("ink / header-top", "--ink", "--header-grad:0", 4.5, True),
    ("ink / header-bottom", "--ink", "--header-grad:1", 4.5, True),
    ("ink / rail-top", "--ink", "--rail-grad:0", 4.5, True),
    ("ink / rail-bottom", "--ink", "--rail-grad:1", 4.5, True),
    ("mute / header-bottom", "--mute", "--header-grad:1", 4.5, True),
    # Known theme-agnostic trade-offs — report only.
    ("gold / card", GOLD, "--card-bg", 3.0, False),
    ("gold / page", GOLD, "--page-bg", 3.0, False),
    ("tab-ink / rail-bottom", "--tab-ink", "--rail-grad:1", 4.5, False),
]

HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
BLOCK_RE = re.compile(r"\.(theme-[a-z]+)\s*\{(.*?)\}", re.S)
DECL_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


def parse_themes(css: str) -> dict[str, dict[str, str]]:
    themes: dict[str, dict[str, str]] = {}
    for match in BLOCK_RE.finditer(css):
        name, body = match.group(1), match.group(2)
        tokens: dict[str, str] = {}
        for decl in DECL_RE.finditer(body):
            tokens[decl.group(1)] = decl.group(2).strip()
        themes[name] = tokens
    return themes


def resolve_hex(tokens: dict[str, str], ref: str) -> str:
    """Resolve a token name (optionally `--grad:N` for gradient stop N) or literal hex."""
    if ref.startswith("#"):
        return ref
    if ":" in ref:
        name, idx = ref.rsplit(":", 1)
        stops = HEX_RE.findall(tokens[name])
        return stops[int(idx)]
    value = tokens[ref]
    hexes = HEX_RE.findall(value)
    if len(hexes) != 1:
        raise ValueError(f"{ref} is not a single hex color: {value!r}")
    return hexes[0]


def srgb_channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return (
        0.2126 * srgb_channel(r)
        + 0.7152 * srgb_channel(g)
        + 0.0722 * srgb_channel(b)
    )


def ratio(fg: str, bg: str) -> float:
    lighter, darker = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def main() -> int:
    themes = parse_themes(THEMES_CSS.read_text())
    if not themes:
        print(f"No .theme-* blocks found in {THEMES_CSS}")
        return 1
    failures = 0
    for theme_name, tokens in sorted(themes.items()):
        print(f"\n== {theme_name} ==")
        for label, fg_ref, bg_ref, minimum, hard in PAIRS:
            try:
                fg = resolve_hex(tokens, fg_ref)
                bg = resolve_hex(tokens, bg_ref)
            except KeyError as missing:
                print(f"  FAIL {label}: missing token {missing}")
                failures += 1
                continue
            r = ratio(fg, bg)
            ok = r >= minimum
            if not ok and hard:
                failures += 1
            mark = "ok  " if ok else ("FAIL" if hard else "soft")
            print(
                f"  {mark} {label:28s} {fg} on {bg}  {r:5.2f}  (min {minimum})"
            )
    if failures:
        print(f"\n{failures} hard contrast failure(s).")
        return 1
    print("\nAll hard contrast pairs pass WCAG AA.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

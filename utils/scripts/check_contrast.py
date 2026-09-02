"""WCAG-AA contrast gate for Mytheca's theme tokens.

Parses the `.theme-*` blocks in web/frontend/styles/themes.css and asserts the
load-bearing text/surface token pairs meet WCAG 2.2 AA in every theme:

- HARD pairs fail the script (exit 1) below their threshold.
- SOFT pairs are reported but do not fail (known, documented trade-offs —
  e.g. the theme-agnostic gold eyebrow accent over light parchment).

It ALSO gates the entity-colour recipe (§2 below). Characters, graph node
types, seals and stat bands carry theme-independent colours chosen for
identity; rendering those raw as text produced 71 contrast failures in the
2026-08-31 baseline audit (#8e2b1c on the Slate card ground measured 1.71:1).
themes.css fixes that by mixing the entity colour toward the theme's own ink,
and this script re-derives the resulting ratio for every entity colour against
every surface in every theme — so the mix percentages in the CSS cannot drift
away from the contrast they were chosen to guarantee.

The percentages are READ FROM themes.css, never hardcoded here. Changing the
CSS changes what this gate checks, which is the only way the two can stay
honest about each other.

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
    ("accent(nontext) / page2", "--accent", "--page-bg", 3.0, True),
    # The RAW accent is a non-text colour: fills, borders, focus rings. Text
    # uses --accent-ink, checked below.
    ("accent(nontext) / card", "--accent", "--card-bg", 3.0, True),
    # card2 is the LIFTED content tier and is lighter than card, so it is the
    # harder of the two — and it was not checked. axe measured accent-on-card2
    # at 4.04:1 on Slate while this table reported accent-on-card passing.
    ("accent(nontext) / card2", "--accent", "--card-bg2", 3.0, True),
    ("accent(nontext) / surface", "--accent", "--surface", 3.0, True),
    ("accent(nontext) / hover", "--accent", "--hover-bg", 3.0, True),
    ("accent(nontext) / field", "--accent", "--field-bg", 3.0, True),
    # The accent as TEXT, on every content surface it can land on.
    ("accent-ink / page", "--accent-ink", "--page-bg", 4.5, True),
    ("accent-ink / card", "--accent-ink", "--card-bg", 4.5, True),
    ("accent-ink / card2", "--accent-ink", "--card-bg2", 4.5, True),
    ("accent-ink / field", "--accent-ink", "--field-bg", 4.5, True),
    ("accent-ink / menu", "--accent-ink", "--menu-bg", 4.5, True),
    ("accent-ink / modal", "--accent-ink", "--modal-bg", 4.5, True),
    ("accent-ink / surface", "--accent-ink", "--surface", 4.5, True),
    ("accent-ink / hover", "--accent-ink", "--hover-bg", 4.5, True),
    # Quoted dialogue inside a free-text passage. The passage sits on --card-bg,
    # but the beat is plain prose that could be re-grounded, so it is checked
    # against every content tier the transcript can put under it.
    ("prose-quote / card", "--prose-quote", "--card-bg", 4.5, True),
    ("prose-quote / card2", "--prose-quote", "--card-bg2", 4.5, True),
    ("prose-quote / page", "--prose-quote", "--page-bg", 4.5, True),
    ("prose-quote / surface", "--prose-quote", "--surface", 4.5, True),
    ("prose-quote / modal", "--prose-quote", "--modal-bg", 4.5, True),
    # NOT a text pair. Accent on the menu ground is 3.67:1 in Slate and 4.40:1 in Ember, so
    # it may carry a border or a glyph inside a popover and must never carry copy — the
    # scene-config pins are the live case (their scope is stated in text, in `--ink`).
    ("accent(nontext) / menu", "--accent", "--menu-bg", 3.0, True),
    # Light text on accent-filled controls (mono-uppercase UI text; the locked
    # design system treats it as large/UI text → 3:1; documented trade-off).
    ("on-accent / accent", "--on-accent", "--accent", 3.0, True),
    ("on-accent / accent-hover", "--on-accent", "--accent-hover", 3.0, True),
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

# --- §2. The entity palette -------------------------------------------------
# Every theme-independent colour the app can attach to an entity and then put
# NEAR text. Sources: web/frontend/lib/graphColors.ts (node + edge types),
# lib/seals.ts, lib/cardArt.ts, and the character colours seeded by
# core/seed.py. A colour added there must be added here, or it is ungated.
ENTITY_COLORS: list[tuple[str, str]] = [
    ("graph/Character", "#B0492F"),
    ("graph/Setting", "#2F7D6B"),
    ("graph/Event", "#C56A1F"),
    ("graph/Faction", "#6B4A8A"),
    ("graph/Secret", "#B0506A"),
    ("graph/Consequence", "#3A5A78"),
    ("edge/positive", "#1F8A5B"),
    ("edge/negative", "#9A3520"),
    ("edge/neutral", "#5B6B7A"),
    ("semantic/gold", "#C8862A"),
    ("semantic/gold-soft", "#A8762A"),
    ("semantic/narrator", "#1F8A82"),
    ("theme/accent-light", "#8E2B1C"),
    ("theme/accent-dark", "#D3694F"),
    ("theme/accent-slate", "#DC634A"),
]

# Surfaces an entity-coloured string can land on. Text sits on content tiers;
# the chrome gradients are covered by the PAIRS table above.
ENTITY_SURFACES = [
    "--card-bg",
    "--card-bg2",
    "--page-bg",
    "--menu-bg",
    "--surface",
    "--hover-bg",
    "--field-bg",
    "--modal-bg",
]

# (token, minimum ratio, what it is for)
ENTITY_DERIVED = [
    ("--entity-ink", 4.5, "small text"),
    ("--entity-ink-strong", 3.0, "large text (>=24px / >=18.66px bold) + non-text marks"),
]

MIX_RE = re.compile(
    r"(--entity-ink(?:-strong)?)\s*:\s*color-mix\(\s*in\s+oklab\s*,"
    r"\s*var\(--entity\)\s+([0-9.]+)%\s*,\s*var\(--ink\)\s*\)"
)

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


# Tokens declared as a mix of the theme's own --accent toward its --ink. They
# are `color-mix()`, not hex, so the gate derives them from the percentage the
# CSS declares — the same read-it-from-the-CSS rule the entity recipe uses, so
# the gate cannot check a colour the browser never renders.
ACCENT_MIX_TOKENS = ("--accent-ink", "--prose-quote")

ACCENT_MIX_RE = re.compile(
    r"(--accent-ink|--prose-quote):\s*color-mix\(\s*in\s+oklab\s*,"
    r"\s*var\(--accent\)\s+([0-9.]+)%"
)


def resolve_hex(tokens: dict[str, str], ref: str) -> str:
    """Resolve a token name (optionally `--grad:N` for gradient stop N) or literal hex.

    The ACCENT_MIX_TOKENS are `color-mix`, not hex, so each is derived here
    from the percentage declared in themes.css.
    """
    if ref in ACCENT_MIX_TOKENS:
        weight = _accent_mix_weight(ref)
        return mix_oklab(resolve_hex(tokens, "--accent"), resolve_hex(tokens, "--ink"), weight)
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


def _accent_mix_weight(token: str) -> float:
    for match in ACCENT_MIX_RE.finditer(THEMES_CSS.read_text()):
        if match.group(1) == token:
            return float(match.group(2)) / 100.0
    raise ValueError(f"themes.css does not declare {token} as a color-mix of --accent")


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


# --- OKLab, so the gate mixes exactly the way `color-mix(in oklab, ...)` does.
# Mixing in sRGB would give a different answer and the gate would be checking a
# colour the browser never renders.
_M1 = (
    (0.4122214708, 0.5363325363, 0.0514459929),
    (0.2119034982, 0.6806995451, 0.1073969566),
    (0.0883024619, 0.2817188376, 0.6299787005),
)
_M2 = (
    (0.2104542553, 0.7936177850, -0.0040720468),
    (1.9779984951, -2.4285922050, 0.4505937099),
    (0.0259040371, 0.7827717662, -0.8086757660),
)
_M1_INV = (
    (1.0, 0.3963377774, 0.2158037573),
    (1.0, -0.1055613458, -0.0638541728),
    (1.0, -0.0894841775, -1.2914855480),
)
_M2_INV = (
    (4.0767416621, -3.3077115913, 0.2309699292),
    (-1.2684380046, 2.6097574011, -0.3413193965),
    (-0.0041960863, -0.7034186147, 1.7076147010),
)


def _linear_to_srgb(c: float) -> float:
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def to_oklab(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    rgb = [srgb_channel(int(h[i : i + 2], 16)) for i in (0, 2, 4)]
    lms = [sum(_M1[i][j] * rgb[j] for j in range(3)) for i in range(3)]
    lms = [abs(v) ** (1 / 3) * (1 if v >= 0 else -1) for v in lms]
    return tuple(sum(_M2[i][j] * lms[j] for j in range(3)) for i in range(3))


def from_oklab(lab: tuple[float, float, float]) -> str:
    lms = [sum(_M1_INV[i][j] * lab[j] for j in range(3)) for i in range(3)]
    lms = [v**3 for v in lms]
    rgb = [sum(_M2_INV[i][j] * lms[j] for j in range(3)) for i in range(3)]
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, round(_linear_to_srgb(c) * 255))) for c in rgb
    )


def mix_oklab(color: str, toward: str, weight: float) -> str:
    """`color-mix(in oklab, <color> <weight*100>%, <toward>)`."""
    a, b = to_oklab(color), to_oklab(toward)
    return from_oklab(tuple(a[i] * weight + b[i] * (1 - weight) for i in range(3)))


def parse_mix_ratios(css: str) -> dict[str, float]:
    """Read the entity mix percentages out of themes.css.

    Hardcoding them here would let the CSS and the gate disagree silently,
    which is the exact failure this whole script exists to prevent.
    """
    found = {m.group(1): float(m.group(2)) / 100.0 for m in MIX_RE.finditer(css)}
    missing = [name for name, _, _ in ENTITY_DERIVED if name not in found]
    if missing:
        raise ValueError(
            "themes.css does not declare "
            + ", ".join(missing)
            + " as `color-mix(in oklab, var(--entity) N%, var(--ink))`"
        )
    return found


def check_entities(
    themes: dict[str, dict[str, str]], ratios: dict[str, float]
) -> int:
    """Every entity colour, derived per theme, against every surface it can sit on."""
    failures = 0
    print("\n== entity colour on surface ==")
    for token, minimum, purpose in ENTITY_DERIVED:
        weight = ratios[token]
        worst = (999.0, "", "", "")
        for theme_name, tokens in sorted(themes.items()):
            ink = resolve_hex(tokens, "--ink")
            for label, raw in ENTITY_COLORS:
                derived = mix_oklab(raw, ink, weight)
                for surface in ENTITY_SURFACES:
                    bg = resolve_hex(tokens, surface)
                    r = ratio(derived, bg)
                    if r < worst[0]:
                        worst = (r, theme_name, label, surface)
                    if r < minimum:
                        failures += 1
                        print(
                            f"  FAIL {token} @ {weight:.0%}  {label} on "
                            f"{surface} in {theme_name}: {r:.2f} < {minimum}"
                        )
        mark = "ok  " if worst[0] >= minimum else "FAIL"
        print(
            f"  {mark} {token:22s} @ {weight:.0%} hue  worst {worst[0]:5.2f} "
            f"(min {minimum}) — {worst[2]} on {worst[3]} in {worst[1]}"
        )
        print(f"       for: {purpose}")
    return failures


def main() -> int:
    css = THEMES_CSS.read_text()
    themes = parse_themes(css)
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
    failures += check_entities(themes, parse_mix_ratios(css))

    if failures:
        print(f"\n{failures} hard contrast failure(s).")
        return 1
    print("\nAll hard contrast pairs pass WCAG AA, entity recipe included.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Render one sample per art style through the real pipeline, offline of the app."""
import sys, random, pathlib
sys.path.insert(0, "/home/bdgr/Agents/Velora/web/backend")
from app.content import art_styles
from app.services import comfyui

OUT = pathlib.Path("/tmp/claude-1000/-home-bdgr-Agents-Velora/6dfcfe80-0e83-45d7-b644-e31b3e38a7bf/scratchpad/samples")
BASE = "http://localhost:8199"
SURFACE = sys.argv[1] if len(sys.argv) > 1 else "portrait"
SUBJECT = sys.argv[2] if len(sys.argv) > 2 else (
    "elderly human woman, weathered sea captain, silver braid, storm-grey eyes, "
    "scarred jaw, salt-stained navy coat with brass buttons, wry half-smile"
)
SIZE = {"portrait": (832, 1216), "scene": (1024, 576), "moment": (1216, 832)}[SURFACE]
SEED = 20260822  # fixed across styles so only the STYLE differs

for style in art_styles.catalog():
    pos, neg = art_styles.apply_style(SUBJECT, "", style, surface=SURFACE)
    lora = style.default_lora
    print(f"\n=== {style.id} | lora={lora or 'BYPASSED'}")
    print("positive:", pos)
    print("negative:", neg)
    img, info = comfyui.generate(
        BASE, "ZiT-Workflow.json",
        positive=pos, negative=neg, seed=SEED, steps=4, cfg=1.0,
        width=SIZE[0], height=SIZE[1], batch_size=1,
        lora_name=lora, lora_strength=style.default_lora_strength,
        lora_enabled=bool(lora),
    )
    p = OUT / f"{SURFACE}-{style.id}.png"
    p.write_bytes(img)
    print("wrote", p, len(img), "bytes")

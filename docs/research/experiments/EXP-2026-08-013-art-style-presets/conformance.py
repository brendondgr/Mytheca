"""Record, per (style × surface), what the emitted ComfyUI graph actually carried.

Deterministic and offline: it builds the same graph `generate()` would queue and reads
it back, rather than trusting that the render "looked right".
"""
import json, sys, pathlib
sys.path.insert(0, "/home/bdgr/Agents/Velora/web/backend")
from app.content import art_styles
from app.services import comfyui

SUBJECTS = {
    "portrait": "elderly human woman, weathered sea captain, silver braid, storm-grey eyes, scarred jaw, salt-stained navy coat with brass buttons, wry half-smile",
    "scene": "fog-bound harbor at dawn, rotting jetties, tide-eaten sea wall, moored hulls, lanterns in the mist, wet timber and brine, cold slack tide",
}
SIZES = {"portrait": (832, 1216), "scene": (1024, 576)}
wf = comfyui.load_workflow("ZiT-Workflow.json")
rows = []
for surface, subject in SUBJECTS.items():
    for style in art_styles.catalog():
        pos, neg = art_styles.apply_style(subject, "", style, surface=surface)
        lora = style.default_lora
        g = comfyui.build_prompt(
            wf, positive=pos, negative=neg, seed=20260822, steps=4, cfg=1.0,
            width=SIZES[surface][0], height=SIZES[surface][1], batch_size=1,
            lora_name=lora, lora_strength=style.default_lora_strength,
            lora_enabled=bool(lora),
        )
        wired = any(
            isinstance(v, list) and len(v) == 2 and str(v[0]) == comfyui.LORA_NODE
            for n in g.values() for v in (n.get("inputs") or {}).values()
        )
        own = {p.strip().lower() for p in style.tags_for(surface).split(",") if p.strip()}
        foreign = {
            p.strip().lower()
            for o in art_styles.catalog() if o.id != style.id
            for p in o.tags_for(surface).split(",") if p.strip()
        } - own
        have = {p.strip().lower() for p in g[comfyui.POSITIVE_NODE]["inputs"]["text"].split(",")}
        rows.append({
            "surface": surface,
            "style": style.id,
            "lora_intended": lora or None,
            "lora_in_graph": g[comfyui.LORA_NODE]["inputs"].get("lora_name") if wired else None,
            "lora_node_wired": wired,
            "own_tags_present": len(own & have),
            "own_tags_total": len(own),
            "foreign_tags_present": len(foreign & have),
        })
        print(rows[-1])

n = len(rows)
ok_lora = sum(1 for r in rows if (r["lora_in_graph"] == r["lora_intended"]))
ok_tags = sum(1 for r in rows if r["own_tags_present"] == r["own_tags_total"])
ok_clean = sum(1 for r in rows if r["foreign_tags_present"] == 0)
out = {
    "rows": rows,
    "summary": {
        "n_conditions": n,
        "lora_state_correct": ok_lora,
        "own_tags_complete": ok_tags,
        "no_foreign_tags": ok_clean,
    },
}
p = pathlib.Path("/home/bdgr/Agents/Velora/docs/research/experiments/EXP-2026-08-013-art-style-presets/data/metrics.json")
p.write_text(json.dumps(out, indent=2) + "\n")
print("\nSUMMARY", out["summary"])

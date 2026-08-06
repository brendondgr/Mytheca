# Contributing to Mytheca

Start with [`docs/skills/global-project-rules/SKILL.md`](docs/skills/global-project-rules/SKILL.md).
It is the canonical entry point: required reading, stack, environment rules,
documentation duties, and the definition of done. `docs/` is the single source of
truth — agent folders (`.claude/`, `.agents/`, `.cursor/`) only point back to it.

## The validation gate

A change is not done until this passes:

```bash
uv run pytest                                    # backend
cd web/frontend && npm test                      # frontend
```

UI changes additionally require an accessibility + responsive pass (keyboard, visible
focus, AA contrast, 320/375/768/1024). Theme-token changes require
`uv run python utils/scripts/check_contrast.py`.

If you skip a check, say so explicitly and record why in
[`docs/checklist.md`](docs/checklist.md).

## Rules that are not negotiable

- `uv` only for Python — never pip, poetry, or conda. npm for the frontend.
- `uv run python app.py` owns Docker and both dev servers. Never run
  `docker compose` yourself.
- Update the relevant `docs/*.md` **in the same change** that alters behaviour.
- Branch off `main`. Commit per completed phase. No push or PR unless asked.

## Running an experiment

Any benchmark, baseline, ablation, or evaluation run is recorded under
`docs/research/experiments/`. The contract is
[`docs/research/AGENT_INSTRUCTIONS.md`](docs/research/AGENT_INSTRUCTIONS.md).

1. `make new-experiment SLUG=<slug>` — scaffolds the folder from templates.
2. Fill `PROTOCOL.md` **before** running anything. Pre-registration is what separates
   an experiment from a fishing expedition, and it writes half the methods section.
3. Run via the recorded entrypoint so the manifest is auto-populated with commit,
   config hash, seeds, environment and compute at write-time.
4. Fill `RESULTS.md`, regenerate figures, run `make validate-research`.
5. Commit the experiment folder in the same PR as any code change it depends on.

**Failed and abandoned runs are recorded, not deleted.** Set `status: failed`, write
what broke, and keep the folder — see
[`EXP-2026-08-001`](docs/research/experiments/EXP-2026-08-001-planner-vs-oneshot-director/)
for a worked example.

Never report a metric in chat or a commit message without also writing it to the
corresponding `manifest.yaml` and `RESULTS.md`. Never hand-edit a figure. Never
hardcode a number in a plotting script.

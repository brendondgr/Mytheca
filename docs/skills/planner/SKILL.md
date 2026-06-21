---
name: planner
description: Use this skill when the user asks to create, refine, or evaluate an implementation plan, roadmap, migration plan, or structured sequence of work before coding in Velora. Plans are detailed, phase-by-phase, commit-per-phase, and validated with pytest + frontend tests.
---

# Plan Creation (Velora)

Use this skill to produce explicit, hierarchical, phase-by-phase implementation plans for Velora work. Save plans under `docs/plans/`.

## Core Reference

Follow the planning format and quality rules in [planner.md](planner.md). The conventions below are already baked into that reference for this project.

## Velora Conventions (locked)

- **Granularity:** full phase-by-phase implementation plans (detailed engineering, not brief outlines).
- **Validation per phase:** backend `uv run pytest` (relevant `utils/tests/backend/...`) and frontend component/route tests. Web/UI phases additionally require an accessibility + responsive pass (`accessibility-mobile` + `ada-compliance`). Recommended hygiene: `ruff`/`mypy`, `tsc`/ESLint.
- **Git workflow:** **commit per phase** — each completed phase ends with a local commit, no automatic push or PR unless the user asks.
- **Audience:** agentic coding workflows and solo implementation.

## When To Use

- "Create a plan", "plan this out", "make a roadmap", "break this into steps".
- Any staged implementation before code changes (new agent, new route, schema migration, streaming feature, DB integration).

## Output Expectations

- Clean Markdown: introduction, gaps & unanswered questions, hierarchical steps, deliverables table.
- Concrete locations: exact files, classes, functions, and directories (use Velora's `web/frontend`, `web/backend/app`, `web/shared/contracts`, `utils/tests/` paths).
- State assumptions for simple gaps; explicitly flag complex gaps that need human input.
- End every phase with the validation + commit action line (see planner.md).

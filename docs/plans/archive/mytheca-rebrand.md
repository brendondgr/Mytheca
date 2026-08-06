# Mytheca Rebrand — Velora → Mytheca

## 1. Introduction

Velora is being rebranded to **Mytheca** ("Myth" + Greek *Bibliotheca* = "Library of Myths"). This is a full rebrand: every user-facing string, every internal source identifier, **and** the infrastructure identifiers (Docker volumes/images, the `VELORA_SKIP_DOCKER` env var, the Postgres user/db, the Neo4j password, and the Qdrant collection) move from `velora` to `mytheca`. The user has explicitly accepted that renaming infra orphans existing local Docker data volumes (a fresh re-seed) and requires updating any local `.env`.

The rename is uniform across three case variants — `Velora → Mytheca`, `VELORA → MYTHECA`, `velora → mytheca` — which by construction covers brand prose, CSS classes (`velora-page`, `velora-rail`, …), keyframes (`veloraGlowPulse`), localStorage keys (`velora-theme`, `velora-font-size`), Docker volumes (`velora_pgdata`), the skip-docker env var, the Qdrant collection (`velora_lore`), DB credentials, and package names in a single sweep. Separately, we integrate the new SVG logo assets: a theme-aware in-app brand mark (dark logo on the light Parchment theme; light logo on the dark Ember/Slate themes), an SVG favicon, and the wordmark logo at the top of a GitHub-polished README.

Work happens in the `rebrand-mytheca` worktree (branched off `main`), committed per phase, and merged back to `main` with the worktree deleted at the end.

## 2. Gaps & Unanswered Questions

- **Rename depth** — *Resolved by the user:* full rename including infrastructure identifiers. Local Docker volumes will be orphaned and re-seeded; the user updates their local `.env` (`DATABASE_URL`, `NEO4J_PASSWORD`, `QDRANT_COLLECTION`, and `VELORA_SKIP_DOCKER` → `MYTHECA_SKIP_DOCKER` if set). This must be surfaced in the final handoff.
- **Header logo form (assumption):** the app header is a "specific thing," so it uses the theme-aware **icon** logo (`Basic.svg` / `Basic-Light.svg`) beside a `MYTHECA` text wordmark, preserving the current 52px header layout. The full text-logo SVGs (`LightText.svg` / `DarkText.svg`) are reserved for the README.
- **README logo (assumption):** per the brief, `LightText.svg` (light-colored wordmark) is used on the README. Because GitHub renders READMEs in both light and dark mode, we use a `<picture>` element that shows `DarkText.svg` in light mode and `LightText.svg` in dark mode, so the wordmark is legible in both — `LightText.svg` remains the designated dark-mode asset.
- **Favicon (assumption):** `Basic.svg` (dark icon) becomes `web/frontend/app/icon.svg`; Next.js App Router auto-emits the `<link rel="icon">`. The legacy `app/favicon.ico` is removed so the old mark can't win.
- **My auto-memory** under `~/.claude/.../memory/` uses `velora-*` filenames — out of repo scope, left untouched (historical notes).
- **Excluded from all sweeps:** `.claude/worktrees/**` (stale sibling worktrees), `node_modules`, `.next`, `.git`, and binary/SVG assets.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Land the brand assets in the repo

- **Locations:** `images/` (rename `DarkText` → `DarkText.svg`), `web/frontend/public/brand/basic.svg` + `basic-light.svg` (icon logos), `web/frontend/app/icon.svg` (dark icon = favicon), remove `web/frontend/app/favicon.ico`.
- **Rationale:** Every later phase (header mark, favicon, README) references these paths; land and `git add` them first so the tree is stable. The four source SVGs are currently untracked — this phase tracks them.
- **Details:** Copy `Basic.svg` → `public/brand/basic.svg`, `Basic-Light.svg` → `public/brand/basic-light.svg`, `Basic.svg` → `app/icon.svg`. Keep the originals in `images/` as the canonical brand kit (README uses `images/LightText.svg` + `images/DarkText.svg`).
- **Action:** No behavior to test yet; confirm files exist and `next` build still resolves `app/icon.svg` (deferred to Phase 3 preview). Commit: `Mytheca Rebrand (1/6) Complete: Landed Mytheca SVG brand kit (icons, favicon source, README wordmarks).`

### Phase 2 — Global case-aware string rename (brand + identifiers + infra)

- **Locations:** all tracked source under `web/`, `docs/`, `utils/`, `app.py`, `pyproject.toml`, `.env.example`, `.claude/` (excluding `.claude/worktrees/**`), root `README.md` prose (README gets a full rewrite in Phase 4, so a light touch here is fine).
- **Rationale:** One deterministic sweep keeps brand text and every identifier consistent, so tests that assert on class names / storage keys / literals are updated in lockstep with the code that produces them.
- **Details:** Apply, per file, in order: `VELORA → MYTHECA`, `Velora → Mytheca`, `velora → mytheca`. This covers: `layout.tsx` metadata title/description, `AppHeader` wordmark text, CSS classes + keyframes in `styles/themes.css` / `app/globals.css` and every `.tsx` using them, storage keys in `lib/theme.ts` + `lib/font-size.ts`, `docker-compose.yml` (volumes, `POSTGRES_USER/PASSWORD/DB`, `NEO4J_AUTH`, image `velora-neo4j`), `config.py` defaults (`database_url`, `neo4j_password`, `qdrant_collection`), `app.py` (`VELORA_SKIP_DOCKER`, prose), `.env.example`, `package.json` name (`velora-frontend`), and doc prose.
- **Validation & Commit:** Run `uv run pytest`, frontend `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build`; fix any assertion/snapshot fallout. Commit: `Mytheca Rebrand (2/6) Complete: Renamed Velora→Mytheca across source, styles, docs, and infrastructure identifiers.`

### Phase 3 — Wire the theme-aware brand mark + favicon

- **Locations:** new `web/frontend/components/layout/BrandMark.tsx` (or inline in `AppHeader.tsx`), CSS in `app/globals.css` / `styles/themes.css` for the theme-keyed background swap, `AppHeader.tsx` (replace the `❖` glyph with the themed icon), `app/icon.svg` (from Phase 1), `app/layout.tsx` metadata icon if needed. Co-located test `AppHeader.test.tsx` if one exists / a new `BrandMark.test.tsx`.
- **Rationale:** The logo must swap with the theme without a flash. A CSS `background-image` on a sized `role="img"` element, keyed on the `.theme-dark` / `.theme-slate` ancestor class (set pre-paint by `themeInitScript`), avoids JS/hydration flicker — dark icon on light theme, light icon on the dark themes.
- **Details:** Default (light/Parchment) → `basic.svg` (dark ink); `.theme-dark`, `.theme-slate` → `basic-light.svg` (cream). Element carries `aria-label="Mytheca"`. Keep the `MYTHECA` wordmark text beside it.
- **Validation & Commit:** `npm test` + `npm run typecheck` + `npm run build`; **accessibility + responsive pass** (keyboard focus, contrast, brand mark visible/legible at 320/375/768/1024, and correct swap under light/dark/slate) verified in the browser preview. Commit: `Mytheca Rebrand (3/6) Complete: Theme-aware Mytheca brand mark in header + SVG favicon.`

### Phase 4 — GitHub-facing README overhaul

- **Locations:** root `README.md`.
- **Rationale:** The README is the front door for anyone browsing the GitHub repo; it must lead with the Mytheca wordmark, explain the "Library of Myths" concept, and present the stack/quickstart cleanly.
- **Details:** Top-of-file centered `<picture>` wordmark (`DarkText.svg` light-mode / `LightText.svg` dark-mode from `images/`), a one-line tagline, concept blurb, a tidy stack/feature section, quickstart, and the existing docs-as-source-of-truth links (paths updated for any renamed docs from Phase 5 if reordered). Follow the `portfolio-readme` guidance for structure and legibility.
- **Validation & Commit:** Verify all intra-repo links resolve and the `<picture>` asset paths exist. Commit: `Mytheca Rebrand (4/6) Complete: Rebuilt README with Mytheca wordmark and GitHub-facing structure.`

### Phase 5 — Rename `velora-*` doc/plan filenames + fix references

- **Locations:** `docs/plans/velora-*.md` (e.g. `velora-rag-implementation.md`), any other `velora`-named docs; update every intra-repo link that points at them (`docs/**`, `README.md`, `CLAUDE.md`).
- **Rationale:** Filenames are part of "adjust the documents"; leaving `velora-` filenames after a full rebrand is inconsistent. Use `git mv` and repoint links so nothing 404s.
- **Details:** `git mv` each file, then grep for the old basenames and update links. Update `docs/checklist.md` with a rebrand entry and note the local-`.env` migration requirement.
- **Validation & Commit:** grep confirms no dangling links to old filenames; `uv run pytest` (docs-only change, sanity) stays green. Commit: `Mytheca Rebrand (5/6) Complete: Renamed velora-* doc filenames and repointed links; checklist updated.`

### Phase 6 — Full gate, merge, cleanup

- **Locations:** whole worktree → `main`.
- **Rationale:** Prove the rebrand is green end-to-end, then integrate and remove the worktree so the repo stays tidy.
- **Details:** Full validation gate: `uv run pytest`, `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`, plus a browser-preview smoke of the header brand mark across the three themes. A final `grep -ri "velora"` (excluding worktrees/deps) should return only intentional residue (none expected). Merge `rebrand-mytheca` into `main`, resolve conflicts, commit, then `git worktree remove` and delete the branch.
- **Validation & Commit:** Full gate green. Commit the merge. Surface the local-`.env` / re-seed migration note to the user.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Brand kit in repo | Tracked SVG logos (icons, favicon source, README wordmarks) | `images/`, `web/frontend/public/brand/`, `web/frontend/app/icon.svg` |
| Global rename | `Velora→Mytheca` across all source, styles, docs, and infra identifiers | `web/**`, `docs/**`, `app.py`, `docker-compose.yml`, `config.py`, `.env.example`, `pyproject.toml` |
| Theme-aware brand mark | Header logo that swaps dark/light with the theme, + SVG favicon | `web/frontend/components/layout/`, `app/globals.css`, `styles/themes.css`, `app/icon.svg` |
| README | GitHub-facing rewrite with Mytheca wordmark | `README.md` |
| Doc filename renames | `velora-*` docs renamed + links repointed | `docs/plans/`, `docs/`, `CLAUDE.md` |
| Tests | Updated/added component tests for header brand mark; existing suites stay green | `web/frontend/components/layout/*.test.tsx`, existing pytest/vitest suites |

"use client";

import { useEffect, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { CloseButton } from "@/components/ui/CloseButton";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { SmartImage } from "@/components/ui/SmartImage";
import * as api from "@/lib/api";
import { API_BASE } from "@/lib/api";
import { buildSummary, type BuildState } from "@/features/library/worldBuild";
import type { PopulateOptions, RosterSource } from "@/lib/types";
import { ArtStylePicker } from "@/components/feature/ArtStylePicker";
import type { ArtStyleId } from "@/lib/api";

/** "6 character files · 3 setting files · 2 lore files" */
function describeFiles(files: { characters: number; settings: number; lore: number }): string {
  const parts = [
    files.characters ? `${files.characters} character file${files.characters === 1 ? "" : "s"}` : "",
    files.settings ? `${files.settings} setting file${files.settings === 1 ? "" : "s"}` : "",
    files.lore ? `${files.lore} lore file${files.lore === 1 ? "" : "s"}` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

/** `/media/...` is served by the backend host, not the Next app. */
function mediaSrc(url: string): string {
  return url.startsWith("http") ? url : `${API_BASE.replace(/\/api$/, "")}${url}`;
}

/**
 * The Create World dialog — and the build console it turns into.
 *
 * Creating a world is the expensive half of authoring: a roster, then a generation per
 * character and place (plus a render each when artwork is on). That used to happen
 * behind a closed dialog with a one-line footer, which read as "it skipped the build".
 * So the dialog now stays open for the whole run: it asks what to build, then shows
 * every step and every entity as it lands, and the author is only taken into the new
 * world once the run reports `done`. A run that fails or is stopped keeps the dialog
 * open with what was built — the world exists either way, so it says so rather than
 * pretending otherwise.
 */
export function BuildWorldModal({
  open,
  build,
  defaults,
  worldTitle,
  sourceFiles,
  onCancel,
  onConfirm,
  onStop,
  onEnter,
}: {
  open: boolean;
  build: BuildState;
  defaults: PopulateOptions;
  worldTitle?: string;
  /** The author's context files, counted by what they were classified as. */
  sourceFiles: { characters: number; settings: number; lore: number };
  onCancel: () => void;
  onConfirm: (options: PopulateOptions) => void;
  onStop: () => void;
  onEnter: () => void;
}) {
  const [enabled, setEnabled] = useState(defaults.enabled);
  const [withArtwork, setWithArtwork] = useState(defaults.withArtwork);
  // Chosen once, up front, for the whole run: a world whose cast is half painted and half
  // photoreal is not a world. `null` = the operator's default from Options.
  const [artStyle, setArtStyle] = useState<ArtStyleId | null>(defaults.artStyle ?? null);
  // Files win by default: if the author uploaded and classified any, the build makes
  // *those* people and places. Inventing is a deliberate choice, never a surprise.
  const hasFiles = sourceFiles.characters + sourceFiles.settings + sourceFiles.lore > 0;
  // Derived, not initialised-once: this component stays mounted while closed, so a
  // `useState` default captured on first mount kept saying "invent" even after the
  // author uploaded and classified files — precisely the surprise being fixed. Until
  // they choose for themselves, the default follows what they actually have.
  const [chosenSource, setChosenSource] = useState<RosterSource | null>(null);
  const source: RosterSource = chosenSource ?? (hasFiles ? "documents" : "invent");
  const setSource = setChosenSource;
  // Artwork is only worth offering when the render server answers, so the checkbox
  // defaults to what ComfyUI actually is right now rather than to a guess.
  const [comfy, setComfy] = useState<"probing" | "up" | "down">("probing");

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    // No synchronous reset to "probing" here: the state already starts there, and on a
    // re-open the last known status is a better thing to show than a flash of unknown
    // (a sync setState in an effect also cascades a render).
    void api
      .checkComfyStatus({})
      .then((res) => {
        if (cancelled) return;
        setComfy(res.ok ? "up" : "down");
        setWithArtwork(res.ok);
      })
      .catch(() => {
        if (!cancelled) setComfy("down");
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  if (!open) return null;

  const asking = build.phase === "ask";
  const running = build.phase === "creating" || build.phase === "building";
  const finished = build.phase === "done" || build.phase === "failed";
  const clean = build.phase === "done" && build.problems.length === 0;

  return (
    <Modal
      open
      // Mid-run the dialog is the only thing reporting progress, so backdrop/Escape
      // must not drop it — Stop is the way out.
      onClose={running ? () => {} : onCancel}
      labelledBy="build-world-title"
      className="sm:w-[520px]"
    >
      <div className="p-[22px_26px_24px]">
        <div className="flex items-start justify-between gap-[14px]">
          <div>
            {/* `--mute` rather than the Eyebrow default `--mute2`: at 10px uppercase
                on the modal panel, mute2 measures ~3.9:1 — under AA. */}
            <Eyebrow tracking="0.2em" color="var(--mute)">
              {running ? "Building" : "Create World"}
            </Eyebrow>
            <h2
              id="build-world-title"
              className="mt-1 font-display text-[22px] font-bold text-ink"
            >
              {asking
                ? "Build the cast and settings?"
                : running
                  ? `Building ${worldTitle || "the world"}…`
                  : build.phase === "done"
                    ? "The world is built."
                    : "The build stopped early."}
            </h2>
          </div>
          {running ? null : <CloseButton onClose={finished ? onEnter : onCancel} />}
        </div>

        <div className="my-[16px] h-[3px] border-t border-b border-t-ink border-b-hair-strong" />

        {asking ? (
          <>
            <p className="font-body text-[14.5px] leading-[1.5] text-ink">
              Mytheca will write this world’s cast and the places your scenes return to —
              each character fleshed out with their voice and starting stats. You’ll
              watch it happen here.
            </p>

            <fieldset className="mt-[16px] flex flex-col gap-[10px] border-0 p-0">
              <legend className="mb-[2px] font-mono text-[10px] tracking-[0.12em] text-mute uppercase">
                Who gets built
              </legend>

              <label className="flex cursor-pointer items-start gap-[10px]">
                <input
                  type="radio"
                  name="build-source"
                  checked={source === "documents"}
                  disabled={!hasFiles}
                  onChange={() => setSource("documents")}
                  className="mt-[3px] h-[14px] w-[14px] shrink-0 accent-[var(--accent)] disabled:opacity-40"
                />
                <span
                  className={
                    hasFiles
                      ? "font-body text-[14px] leading-[1.45] text-ink"
                      : "font-body text-[14px] leading-[1.45] text-mute"
                  }
                >
                  The people and places in my files
                  <span className="block font-body text-[12.5px] text-ink-soft">
                    {hasFiles ? describeFiles(sourceFiles) : "No context files uploaded."}
                  </span>
                </span>
              </label>

              <label className="flex cursor-pointer items-start gap-[10px]">
                <input
                  type="radio"
                  name="build-source"
                  checked={source === "invent"}
                  onChange={() => setSource("invent")}
                  className="mt-[3px] h-[14px] w-[14px] shrink-0 accent-[var(--accent)]"
                />
                <span className="font-body text-[14px] leading-[1.45] text-ink">
                  Invent a cast from the premise
                  <span className="block font-body text-[12.5px] text-ink-soft">
                    Mytheca makes up who lives here. Your files still ground the writing.
                  </span>
                </span>
              </label>
            </fieldset>

            <fieldset className="mt-[18px] flex flex-col gap-[12px] border-0 p-0">
              <legend className="sr-only">What to build</legend>

              <label className="flex cursor-pointer items-start gap-[10px]">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                  className="mt-[3px] h-[15px] w-[15px] shrink-0 accent-[var(--accent)]"
                />
                <span className="font-body text-[14px] leading-[1.45] text-ink">
                  Write the characters and settings
                  <span className="block font-body text-[12.5px] text-ink-soft">
                    A few minutes — a generation per character and place.
                  </span>
                </span>
              </label>

              <label className="flex cursor-pointer items-start gap-[10px]">
                <input
                  type="checkbox"
                  checked={withArtwork}
                  disabled={!enabled || comfy !== "up"}
                  onChange={(e) => setWithArtwork(e.target.checked)}
                  className="mt-[3px] h-[15px] w-[15px] shrink-0 accent-[var(--accent)] disabled:opacity-40"
                />
                <span
                  className={
                    enabled && comfy === "up"
                      ? "font-body text-[14px] leading-[1.45] text-ink"
                      : "font-body text-[14px] leading-[1.45] text-mute"
                  }
                >
                  Also paint portraits and scene art
                  <span className="block font-body text-[12.5px] text-ink-soft">
                    {comfy === "probing"
                      ? "Checking for a ComfyUI server…"
                      : comfy === "up"
                        ? "ComfyUI is running — adds a render per character and place."
                        : "No ComfyUI server is answering, so there is nothing to render with."}
                  </span>
                </span>
              </label>

              {enabled && withArtwork && comfy === "up" ? (
                <ArtStylePicker
                  value={artStyle}
                  onChange={setArtStyle}
                  label="Style for every image in this build"
                  className="ml-[25px]"
                />
              ) : null}
            </fieldset>
          </>
        ) : (
          <BuildConsole build={build} />
        )}

        <div className="mt-[22px] flex flex-wrap items-center justify-end gap-[10px]">
          {asking ? (
            <>
              <Button variant="ghost" onClick={onCancel}>
                Cancel
              </Button>
              <Button
                variant="secondary"
                onClick={() =>
                  onConfirm({ enabled: false, withArtwork: false, source, artStyle })
                }
              >
                Just the world
              </Button>
              <Button
                onClick={() =>
                  onConfirm({
                    enabled,
                    withArtwork: enabled && withArtwork && comfy === "up",
                    source,
                    artStyle,
                  })
                }
              >
                {enabled ? "Create & Build" : "Create World"}
              </Button>
            </>
          ) : running ? (
            <>
              <span className="mr-auto font-mono text-[10px] tracking-[0.12em] text-mute2 uppercase">
                Stay here — the world opens when it’s built.
              </span>
              <Button variant="ghost" onClick={onStop}>
                Stop
              </Button>
            </>
          ) : (
            <>
              <span className="mr-auto font-mono text-[10px] tracking-[0.12em] text-mute2 uppercase">
                {buildSummary(build)}
              </span>
              <Button onClick={onEnter}>
                {clean ? "Enter the world" : "Enter the world anyway"}
              </Button>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}

/** The live checklist: what is happening, what has landed, and what went wrong. */
function BuildConsole({ build }: { build: BuildState }) {
  const running = build.phase === "creating" || build.phase === "building";
  const characters = build.entities.filter((e) => e.kind === "character");
  const settings = build.entities.filter((e) => e.kind === "setting");

  return (
    <div>
      <p
        aria-live="polite"
        className="flex items-center gap-[8px] font-body text-[14px] text-ink"
      >
        {running ? (
          <span
            aria-hidden
            className="inline-block h-[9px] w-[9px] shrink-0 rounded-full bg-accent animate-pulse"
          />
        ) : null}
        <span>
          {build.step ||
            (build.phase === "failed"
              ? (build.error ?? "The build stopped.")
              : `Built ${buildSummary(build)}.`)}
        </span>
        {running && build.total > 1 ? (
          <span className="ml-auto shrink-0 font-mono text-[11px] text-mute">
            {build.index} / {build.total}
          </span>
        ) : null}
      </p>

      {build.phase === "failed" && build.error && build.step === "" && build.entities.length ? (
        <p role="alert" className="mt-[10px] font-body text-[13px] text-danger">
          {build.error}
        </p>
      ) : null}

      {/* What the run said it would build, before it built it — so the author sees the
          roster (and that it came from their files) rather than entities appearing from
          nowhere. */}
      {build.plan ? (
        <div className="mt-[14px] rounded-[4px] border border-hair-strong bg-field px-[12px] py-[10px]">
          <span className="font-mono text-[10px] tracking-[0.12em] text-mute uppercase">
            {build.plan.source === "documents" ? "From your files" : "Invented"}
          </span>
          <p className="mt-[4px] font-body text-[13px] leading-[1.45] text-ink">
            {[...build.plan.characters, ...build.plan.settings].map((e) => e.name).join(" · ") ||
              "Nothing to build."}
          </p>
          {build.plan.note ? (
            <p className="mt-[4px] font-body text-[12px] text-ink-soft">{build.plan.note}</p>
          ) : null}
        </div>
      ) : null}

      <EntityList label="Characters" entities={characters} />
      <EntityList label="Settings" entities={settings} />

      {build.problems.length ? (
        <div className="mt-[16px] border-t border-hair-strong pt-[12px]">
          <span className="font-mono text-[10px] tracking-[0.12em] text-mute2 uppercase">
            Skipped
          </span>
          <ul className="mt-[6px] flex flex-col gap-[4px]">
            {build.problems.map((p, i) => (
              <li key={i} className="font-body text-[12.5px] leading-[1.4] text-ink-soft">
                {p}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function EntityList({
  label,
  entities,
}: {
  label: string;
  entities: BuildState["entities"];
}) {
  if (!entities.length) return null;
  return (
    <div className="mt-[16px]">
      <span className="font-mono text-[10px] tracking-[0.12em] text-mute2 uppercase">
        {label} ({entities.length})
      </span>
      <ul className="mt-[8px] flex flex-col gap-[8px]">
        {entities.map((e) => (
          <li key={e.id} className="flex items-center gap-[10px]">
            <SmartImage
              src={e.image ? mediaSrc(e.image) : null}
              alt=""
              aspect="1 / 1"
              className="h-[34px] w-[34px] shrink-0 rounded-[3px] border border-cardbd"
              placeholder={
                <span
                  aria-hidden
                  className="flex h-full w-full items-center justify-center bg-field font-mono text-[11px] text-mute"
                >
                  ✓
                </span>
              }
            />
            <span className="min-w-0">
              <span className="block truncate font-body text-[14px] text-ink">{e.name}</span>
              {e.role ? (
                <span className="block truncate font-body text-[12px] text-ink-soft">
                  {e.role}
                </span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

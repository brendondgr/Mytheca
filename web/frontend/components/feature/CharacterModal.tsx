"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { TextField } from "@/components/ui/TextField";
import { TextArea } from "@/components/ui/TextArea";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { Monogram } from "@/components/ui/Monogram";
import { useDelayedFlag } from "@/hooks/use-delayed-flag";
import { ContextFilesPanel } from "@/components/feature/ContextFilesPanel";
import { SourceDocumentsPanel } from "@/components/feature/SourceDocumentsPanel";
import { VoiceSamplesEditor } from "@/components/feature/VoiceSamplesEditor";
import {
  ProcessProgress,
  type ProcessStep,
} from "@/components/feature/ProcessProgress";
import { docsForDraft } from "@/lib/readDocs";
import { PortraitModal } from "@/components/feature/PortraitModal";
import { mediaUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import { monoOf } from "@/lib/monogram";
import { PALETTE } from "@/lib/seed-data";
import type { useLibraryState } from "@/features/library/useLibraryState";

const SEG = "font-mono text-eyebrow tracking-[0.06em] px-lg py-sm cursor-pointer";
const LINK =
  "cursor-pointer font-mono text-eyebrow tracking-[0.08em] text-accent-ink uppercase enabled:hover:underline disabled:opacity-40";

/** The major stages of an agentic character draft (keys = lib.draftStage). */
const CHARACTER_DRAFT_STEPS: ProcessStep[] = [
  { key: "identity", label: "Identity" },
  { key: "voice", label: "Voice & tone" },
  { key: "stats", label: "Starting stats" },
];

/**
 * Agentic Character Creator modal — the character counterpart to the storyline creator.
 *
 * The author writes a character here (by hand or by prompting Mytheca), fleshing
 * out the by-hand fields plus the base-identity prose (Appearance / Background /
 * Personality). A Portrait section turns the description into watercolor ComfyUI
 * prompts and renders a persisted WebP avatar; a Starting-stats section proposes
 * values keyed to the world's stat schema (saved with the character). A detached
 * context-files column grounds a single generation (never persisted — no RAG).
 *
 * Everything produced is the character's *own* base identity (§1 node
 * properties) — no graph structure is built here.
 */
export function CharacterModal({ lib }: { lib: ReturnType<typeof useLibraryState> }) {
  // Portrait editor pop-up open state — declared before any early return so the
  // hook order stays stable (rules-of-hooks).
  const [portraitOpen, setPortraitOpen] = useState(false);
  // Same flag drives both Save and Delete (they can't run at once); delayed so
  // a save/delete that resolves quickly never flashes a spinner.
  const busy = useDelayedFlag(lib.pending);
  const m = lib.modal;
  if (!m || m.type !== "character") return null;
  const d = lib.draft;
  const agentic = m.mode === "agentic";
  const isEdit = m.editId != null;
  const color = d.color || "#8E2B1C";
  const mono = monoOf(d.name || "");
  const seedText = (d._prompt ?? "").trim();
  // Drafting needs either a seed sentence or at least one Draft-tagged reference file.
  const canDraft = Boolean(seedText) || docsForDraft(d._docFiles ?? []).length > 0;
  const portraitUrl = d.portrait ? mediaUrl(d.portrait) : null;
  const hasDescription = Boolean(
    (d.name || d.appearance || d.traits || d.personality || "").toString().trim(),
  );
  const canRenderPortrait = Boolean((d._portraitPositive ?? "").trim());
  const voiceSamples = d._voiceSamples ?? [];
  const stats = d._startingStats ?? [];
  // Live highlight for the field Mytheca is writing right now, and whether an
  // agentic draft flow is currently running (drives the progress stepper).
  const fieldClass = (key: string) =>
    lib.activeField === key ? "mytheca-field-active" : undefined;
  const drafting = lib.generating || lib.generatingVoice || lib.generatingStats;

  function setStatValue(key: string, raw: string) {
    const value = Number(raw);
    lib.setDraft(
      "_startingStats",
      stats.map((p) =>
        p.key === key
          ? { ...p, value: Math.max(p.min, Math.min(p.max, Number.isFinite(value) ? value : p.value)) }
          : p,
      ),
    );
  }

  return (
    <Modal
      open
      onClose={lib.closeModal}
      labelledBy="character-modal-title"
      className="sm:w-[560px] md:w-[920px] lg:w-[1120px]"
      externalClose
      splitScroll
    >
      <div className="lg:flex lg:min-h-0 lg:flex-1 lg:items-stretch">
        {/* ── Main column (own scroll on lg+) ─────────────────────────── */}
        <div className="min-w-0 p-[22px_26px_24px] lg:flex-1 lg:min-h-0 lg:overflow-y-auto">
          {/* Header — title left; avatar preview + accent picker right. */}
          <div className="flex flex-wrap items-end justify-between gap-x-xl gap-y-lg">
            <div
              id="character-modal-title"
              className="min-w-0 font-display text-step-2 font-bold text-ink"
            >
              {isEdit ? "Edit Character" : "New Character"}
            </div>

            <div className="flex items-center gap-md">
              <Monogram
                mono={mono}
                color={color}
                size={48}
                ring={3}
                fontSize={18}
                src={portraitUrl ?? undefined}
                alt={portraitUrl ? `Portrait of ${d.name || "the character"}` : undefined}
              />
              <div
                role="group"
                aria-label="Accent color"
                className="flex max-w-[180px] flex-wrap gap-xs"
              >
                {PALETTE.map((col) => (
                  <button
                    key={col}
                    type="button"
                    aria-label={`Accent ${col}`}
                    aria-pressed={d.color === col}
                    onClick={() => lib.setDraft("color", col)}
                    className="h-[20px] w-[20px] rounded-full"
                    style={{
                      background: col,
                      boxShadow:
                        d.color === col
                          ? `0 0 0 2px var(--modal-bg), 0 0 0 4px ${col}`
                          : "0 0 0 1px rgba(0,0,0,.15)",
                    }}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Mode toggle — mobile/tablet only. */}
          <div className="mt-lg inline-flex overflow-hidden rounded-full border border-field-bd bg-card md:hidden">
            <button
              type="button"
              onClick={() => lib.setMode("manual")}
              className={cn(SEG, agentic ? "bg-transparent text-mute" : "bg-accent text-[#F6ECDA]")}
            >
              ✎ By hand
            </button>
            <button
              type="button"
              onClick={() => lib.setMode("agentic")}
              className={cn(SEG, agentic ? "bg-accent text-[#F6ECDA]" : "bg-transparent text-mute")}
            >
              ❖ Agentically
            </button>
          </div>
          <div className="my-lg h-[3px] border-t border-b border-t-ink border-b-hair-strong" />

          {/* Live draft progress — which stage Mytheca is on right now. */}
          {drafting ? (
            <ProcessProgress
              className="mb-lg"
              label="Character draft progress"
              steps={CHARACTER_DRAFT_STEPS}
              activeKey={lib.draftStage}
            />
          ) : null}

          {/* By-hand form (left) + agentic Draft with Mytheca (right). */}
          <div className="md:flex md:items-stretch">
            <div className={cn("md:min-w-0 md:flex-1 md:pr-xl", agentic && "hidden md:block")}>
              {d._ai ? (
                <div className="mb-4 flex items-center gap-sm rounded-[0_3px_3px_0] border-l-[3px] border-l-narrator bg-[rgba(31,111,107,.12)] p-[9px_12px]">
                  <span aria-hidden className="text-label text-narrator-ink">
                    ❖
                  </span>
                  <span className="font-body text-label text-ink">
                    Drafted by Mytheca — review &amp; refine, then save.
                  </span>
                </div>
              ) : null}

              <div className="grid grid-cols-1 gap-lg sm:grid-cols-2">
                <TextField
                  label="Display name"
                  placeholder="e.g. Captain Doran Hale"
                  value={d.name || ""}
                  onChange={(e) => lib.setDraft("name", e.target.value)}
                  className={fieldClass("name")}
                />
                <TextField
                  label="Role / archetype"
                  placeholder="e.g. Lawful Blocker"
                  value={d.role || ""}
                  onChange={(e) => lib.setDraft("role", e.target.value)}
                  className={fieldClass("role")}
                />
              </div>
              <TextField
                label="Personality traits"
                placeholder="Dutiful · Rigid · Honourable"
                value={d.traits || ""}
                onChange={(e) => lib.setDraft("traits", e.target.value)}
                className={cn("mt-lg", fieldClass("traits"))}
              />
              {/* Voice — speech style + a (non-functional) voice-sample upload that
                  will feed text-to-speech later. */}
              <div className="mt-lg flex flex-col gap-md sm:flex-row sm:items-end">
                <TextField
                  label="Voice / speech style"
                  placeholder="Formal and terse, by the book."
                  value={d.speech || ""}
                  onChange={(e) => lib.setDraft("speech", e.target.value)}
                  className={cn("sm:flex-1", fieldClass("speech"))}
                />
                <div className="sm:w-[160px] sm:flex-none">
                  <FieldLabel>Voice sample</FieldLabel>
                  <button
                    type="button"
                    disabled
                    aria-disabled="true"
                    title="Coming soon — voice samples will drive text-to-speech."
                    className="flex w-full cursor-not-allowed flex-col items-center gap-3xs rounded-xs border border-dashed border-cardbd bg-field/40 px-sm py-sm text-center opacity-70"
                  >
                    <span aria-hidden className="text-body-sm text-mute">
                      ⤓
                    </span>
                    <span className="font-mono text-eyebrow tracking-[0.08em] text-mute uppercase">
                      Upload · soon
                    </span>
                  </button>
                </div>
              </div>
              <TextArea
                label="Appearance"
                placeholder="Physical look — species/race, age, build, features, dress."
                rows={3}
                value={d.appearance || ""}
                onChange={(e) => lib.setDraft("appearance", e.target.value)}
                className={cn("mt-lg", fieldClass("appearance"))}
              />
              <TextArea
                label="Background"
                placeholder="Backstory — where they come from, what shaped them."
                rows={4}
                value={d.background || ""}
                onChange={(e) => lib.setDraft("background", e.target.value)}
                className={cn("mt-lg", fieldClass("background"))}
              />
              <TextArea
                label="Personality"
                placeholder="The fuller sheet — temperament, values, fears, mannerisms."
                rows={4}
                value={d.personality || ""}
                onChange={(e) => lib.setDraft("personality", e.target.value)}
                className={cn("mt-lg", fieldClass("personality"))}
              />
            </div>

            {/* Agentic draft panel — describe the character; Mytheca drafts it. */}
            <aside
              className={cn(
                "mt-lg md:mt-0 md:w-[300px] md:shrink-0 md:border-l md:border-hair-strong md:pl-xl",
                !agentic && "hidden md:block",
              )}
            >
              {/* Portrait — compact preview + Edit-image trigger (the editor is a
                  pop-up). Sits above Draft with Mytheca in this column. */}
              <div className="mb-lg border-b border-hair-strong pb-lg">
                <FieldLabel>Portrait</FieldLabel>
                <div
                  className="overflow-hidden rounded-sm border border-cardbd bg-field"
                  style={{ borderColor: color }}
                >
                  {portraitUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element -- generated portrait from our media mount
                    <img
                      src={portraitUrl}
                      alt={`Portrait of ${d.name || "the character"}`}
                      className="aspect-square w-full object-cover"
                    />
                  ) : (
                    <div className="flex aspect-square w-full flex-col items-center justify-center gap-sm px-sm text-center">
                      <Monogram mono={mono} color={color} size={56} ring={3} fontSize={22} />
                      <span className="font-mono text-eyebrow tracking-[0.1em] text-mute2 uppercase">
                        No portrait yet
                      </span>
                    </div>
                  )}
                </div>
                <Button
                  variant="secondary"
                  onClick={() => setPortraitOpen(true)}
                  className="mt-sm w-full"
                >
                  ✎ Edit image
                </Button>
              </div>

              <Eyebrow tracking="0.2em" entity="#A8762A" className="mb-sm block">
                ❖ Draft with Mytheca
              </Eyebrow>
              <p className="mb-sm font-body text-body-sm text-ink">
                Describe the character in a sentence —{" "}
                <span className="text-ink-soft italic">Mytheca drafts the rest.</span>
              </p>
              <TextArea
                aria-label="Describe the character to draft"
                rows={4}
                placeholder="e.g. A weary harbor smuggler who owes the Drowned Court and secretly informs for the Tidewatch…"
                value={d._prompt || ""}
                onChange={(e) => lib.setDraft("_prompt", e.target.value)}
              />
              <Button
                onClick={lib.draftCharacter}
                disabled={!canDraft || lib.generating}
                className="mt-md w-full"
              >
                {lib.generating ? "Drafting…" : "❖ Draft with Mytheca"}
              </Button>
              <Button
                variant="ghost"
                onClick={lib.closeModal}
                className="mt-sm w-full md:hidden"
              >
                Cancel
              </Button>
              {lib.error ? (
                <p role="alert" className="mt-4 font-body text-label text-accent-ink md:hidden">
                  {lib.error}
                </p>
              ) : null}
              {isEdit && m.editId ? (
                <SourceDocumentsPanel
                  storylineId={lib.activeStorylineId}
                  entityType="character"
                  entityId={m.editId}
                />
              ) : null}
            </aside>
          </div>

          {/* Voice & Tone — sits ABOVE Starting stats: voice is defined first. */}
          <div
            className={cn(
              "mt-lg border-t border-hair-strong pt-lg",
              agentic && "hidden md:block",
            )}
          >
            <div className="flex items-end justify-between gap-sm">
              <FieldLabel>Voice &amp; tone</FieldLabel>
              <button
                type="button"
                onClick={lib.proposeVoiceSamples}
                disabled={lib.generatingVoice}
                className={cn(LINK, "mb-xs")}
              >
                {lib.generatingVoice
                  ? "Proposing…"
                  : voiceSamples.length
                    ? "❖ Redo"
                    : "❖ Propose"}
              </button>
            </div>
            <p className="mb-sm font-body text-eyebrow text-ink-soft">
              A past situation and this character&apos;s single response to it, in
              their own voice — not a back-and-forth. Derived from their
              background &amp; personality, saved with the character, and used to
              keep their voice consistent in play.
            </p>
            <VoiceSamplesEditor
              samples={voiceSamples}
              onChange={(next) => lib.setDraft("_voiceSamples", next)}
              looseness={typeof d.looseness === "number" ? d.looseness : null}
              onLoosenessChange={(n) => lib.setDraft("looseness", n)}
            />
          </div>

          {/* Starting stats — full-width row: propose → review → save with character. */}
          <div
            className={cn(
              "mt-lg border-t border-hair-strong pt-lg",
              agentic && "hidden md:block",
            )}
          >
            <div className="flex items-end justify-between gap-sm">
              <FieldLabel>Starting stats</FieldLabel>
              <button
                type="button"
                onClick={lib.proposeStartingStats}
                disabled={lib.generatingStats}
                className={cn(LINK, "mb-xs")}
              >
                {lib.generatingStats ? "Proposing…" : stats.length ? "❖ Redo" : "❖ Propose"}
              </button>
            </div>
            <p className="mb-sm font-body text-eyebrow text-ink-soft">
              Proposed values for this world&apos;s stats — review and adjust; they
              are saved with the character.
            </p>
            {stats.length ? (
              <ul className="flex flex-col gap-sm">
                {stats.map((p) => (
                  <li
                    key={p.key}
                    className="rounded-sm border border-cardbd bg-field px-sm py-sm"
                  >
                    <div className="flex items-center justify-between gap-sm">
                      <span className="font-body text-body-sm text-ink">{p.displayName}</span>
                      <label className="flex items-center gap-xs">
                        <span className="font-mono text-tag tracking-[0.06em] text-mute2">
                          {p.min}–{p.max}
                        </span>
                        <input
                          type="number"
                          aria-label={`${p.displayName} starting value`}
                          min={p.min}
                          max={p.max}
                          value={p.value}
                          onChange={(e) => setStatValue(p.key, e.target.value)}
                          className="w-[64px] rounded-xs border border-field-bd bg-card px-sm py-2xs text-right font-mono text-field text-ink focus:border-accent focus:outline-none"
                        />
                      </label>
                    </div>
                    {p.rationale ? (
                      <p className="mt-2xs font-body text-eyebrow text-mute italic">{p.rationale}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="font-body text-eyebrow text-mute">
                No stats proposed yet — Propose to suggest starting values (only when
                this world defines stats).
              </p>
            )}
            {isEdit && stats.length ? (
              <Button
                variant="ghost"
                onClick={() => m.editId && lib.applyStartingStats(m.editId)}
                disabled={lib.applyingStats}
                className="mt-sm"
              >
                {lib.applyingStats ? "Saving stats…" : "Save stats now"}
              </Button>
            ) : null}
          </div>

          {/* Footer — error + actions. */}
          <div className={cn(agentic && "hidden md:block")}>
            {lib.error ? (
              <p role="alert" className="mt-4 font-body text-label text-accent-ink">
                {lib.error}
              </p>
            ) : null}
            <div
              className="mt-lg flex items-center justify-between gap-sm"
              aria-busy={lib.pending || undefined}
            >
              {isEdit ? (
                <button
                  type="button"
                  onClick={lib.deleteEntity}
                  disabled={lib.pending}
                  aria-busy={busy || undefined}
                  aria-label={busy ? "Deleting character" : undefined}
                  className="relative cursor-pointer p-xs font-mono text-eyebrow tracking-[0.06em] text-accent-ink uppercase hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span className={cn("inline-flex items-center", busy && "invisible")}>
                    Delete
                  </span>
                  {busy ? (
                    <span className="absolute inset-0 flex items-center justify-center">
                      <Spinner size={12} />
                    </span>
                  ) : null}
                </button>
              ) : (
                <span />
              )}
              <div className="flex gap-sm">
                <Button variant="ghost" onClick={lib.closeModal}>
                  Cancel
                </Button>
                <Button
                  onClick={lib.submit}
                  disabled={!lib.isValid || lib.pending}
                  loading={busy}
                  loadingLabel={isEdit ? "Saving character" : "Creating character"}
                >
                  {isEdit ? "Save Changes" : "Add to Cast"}
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* ── Detached context-files column ────────────────────────────── */}
        <ContextFilesPanel
          docFiles={d._docFiles ?? []}
          setDocFiles={(docs) => lib.setDraft("_docFiles", docs)}
          inputId="character-docs-input"
          show={agentic}
          scroll
        />
      </div>

      {/* Portrait editor pop-up — prompts, generate, and the rendered preview. */}
      <PortraitModal
        open={portraitOpen}
        onClose={() => setPortraitOpen(false)}
        name={d.name || ""}
        mono={mono}
        color={color}
        portraitUrl={portraitUrl}
        positive={d._portraitPositive || ""}
        negative={d._portraitNegative || ""}
        onPositiveChange={(v) => lib.setDraft("_portraitPositive", v)}
        onNegativeChange={(v) => lib.setDraft("_portraitNegative", v)}
        hasDescription={hasDescription}
        generatingPrompts={lib.generatingPrompts}
        onGeneratePrompts={lib.generatePortraitPrompts}
        canRenderPortrait={canRenderPortrait}
        generatingPortrait={lib.generatingPortrait}
        onGeneratePortrait={lib.generatePortrait}
        error={lib.error}
        activeField={lib.activeField}
        artStyle={lib.artStyle}
        onArtStyleChange={lib.setArtStyle}
      />
    </Modal>
  );
}

"use client";

import { Eyebrow } from "@/components/ui/Eyebrow";
import { TextField } from "@/components/ui/TextField";
import { Monogram } from "@/components/ui/Monogram";
import { mediaUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import { monoOf } from "@/lib/monogram";
import type { ProposedCharacter, ProposedSetting, ProposedWorld } from "@/lib/types";
import type { PlanConcepts } from "@/features/library/storylineCreator";

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="flex-none cursor-pointer rounded-[3px] px-[6px] text-[16px] leading-none text-mute hover:text-danger focus-visible:text-danger"
    >
      ×
    </button>
  );
}

/** A "drafting…" placeholder card for a blueprint concept not yet fleshed out. */
function PendingCard({ concept }: { concept: string }) {
  return (
    <li className="rounded-[4px] border border-dashed border-cardbd bg-field/50 px-[10px] py-[9px]">
      <div className="flex items-center gap-[8px]">
        <span
          aria-hidden
          className="h-[34px] w-[34px] flex-none animate-pulse rounded-full border border-cardbd bg-card2 motion-reduce:animate-none"
        />
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[10px] tracking-[0.1em] text-accent uppercase">Drafting…</p>
          <p className="mt-[3px] truncate font-body text-[12.5px] text-ink-soft">{concept}</p>
        </div>
      </div>
    </li>
  );
}

function CharacterCard({
  c,
  index,
  building,
  committing,
  active,
  onUpdate,
  onRemove,
}: {
  c: ProposedCharacter;
  index: number;
  building: boolean;
  committing: boolean;
  active?: boolean;
  onUpdate: (index: number, patch: Partial<ProposedCharacter>) => void;
  onRemove: (index: number) => void;
}) {
  // While ComfyUI renders a portrait at commit, show a pulsing avatar until it lands.
  const rendering = committing && !c.portrait;
  return (
    <li
      className={cn(
        "rounded-[4px] border border-cardbd bg-field px-[10px] py-[9px]",
        active && "velora-field-active",
      )}
    >
      <div className="flex items-start gap-[10px]">
        <Monogram
          mono={monoOf(c.name)}
          color={c.color || "#8E2B1C"}
          size={40}
          src={c.portrait ? mediaUrl(c.portrait) : null}
          alt={c.portrait ? `${c.name} portrait` : undefined}
          className={cn(rendering && "animate-pulse motion-reduce:animate-none")}
        />
        <div className="min-w-0 flex-1">
          {building ? (
            <p className="truncate font-display text-[15px] font-bold text-ink">{c.name}</p>
          ) : (
            <TextField
              aria-label={`Character ${index + 1} name`}
              value={c.name}
              onChange={(e) => onUpdate(index, { name: e.target.value })}
            />
          )}
          <p className="mt-[5px] font-mono text-[10px] tracking-[0.04em] text-mute2">
            {c.role}
            {c.traits ? ` · ${c.traits}` : ""}
            {rendering ? " · rendering portrait…" : ""}
          </p>
          {c.voiceSamples?.length ? (
            <p className="mt-[4px] font-mono text-[10px] tracking-[0.04em] text-accent">
              ❖ {c.voiceSamples.length} voice sample
              {c.voiceSamples.length === 1 ? "" : "s"}
            </p>
          ) : null}
        </div>
        {!building ? (
          <RemoveButton label={`Remove ${c.name}`} onClick={() => onRemove(index)} />
        ) : null}
      </div>
    </li>
  );
}

function SettingCard({
  s,
  index,
  building,
  committing,
  active,
  onUpdate,
  onRemove,
}: {
  s: ProposedSetting;
  index: number;
  building: boolean;
  committing: boolean;
  active?: boolean;
  onUpdate: (index: number, patch: Partial<ProposedSetting>) => void;
  onRemove: (index: number) => void;
}) {
  const rendering = committing && !s.image;
  return (
    <li
      className={cn(
        "overflow-hidden rounded-[4px] border border-cardbd bg-field",
        active && "velora-field-active",
      )}
    >
      {s.image ? (
        // eslint-disable-next-line @next/next/no-img-element -- generated art from our media mount
        <img
          src={mediaUrl(s.image)}
          alt={`${s.name} scene art`}
          className="aspect-[16/9] w-full object-cover"
        />
      ) : rendering ? (
        <div className="flex aspect-[16/9] w-full animate-pulse items-center justify-center bg-card2 font-mono text-[10px] tracking-[0.1em] text-mute uppercase motion-reduce:animate-none">
          Rendering scene art…
        </div>
      ) : null}
      <div className="px-[10px] py-[9px]">
        <div className="flex items-start gap-[8px]">
          <div className="min-w-0 flex-1">
            {building ? (
              <p className="truncate font-display text-[15px] font-bold text-ink">{s.name}</p>
            ) : (
              <TextField
                aria-label={`Setting ${index + 1} name`}
                value={s.name}
                onChange={(e) => onUpdate(index, { name: e.target.value })}
              />
            )}
            <p className="mt-[5px] font-mono text-[10px] tracking-[0.04em] text-mute2">
              {s.type}
              {s.desc ? ` · ${s.desc}` : ""}
            </p>
          </div>
          {!building ? (
            <RemoveButton label={`Remove ${s.name}`} onClick={() => onRemove(index)} />
          ) : null}
        </div>
      </div>
    </li>
  );
}

/**
 * The New Storyline page's right column while a world is being built agentically.
 * It renders the cast and settings **as they stream in**: the blueprint seeds
 * "drafting…" skeleton cards (`planConcepts`), each `character`/`setting` event
 * fills its slot, and — during *Create World* — portraits / scene art pop in
 * (`committing`). Once the build finishes it becomes the reviewable proposal
 * (editable names, removal, the image-generation toggle, discard) — absorbing the
 * old `ProposedWorldReview`.
 */
export function WorldBuildPanel({
  proposed,
  planConcepts,
  building,
  buildStage,
  activeEntity = null,
  renderingImages = false,
  onUpdateCharacter,
  onRemoveCharacter,
  onUpdateSetting,
  onRemoveSetting,
  onDiscard,
  imagesAvailable,
  generateImages,
  onToggleImages,
}: {
  proposed: ProposedWorld | null;
  planConcepts: PlanConcepts | null;
  building: boolean;
  buildStage: string | null;
  /** The cast/setting card being drafted right now (live highlight). */
  activeEntity?: { type: "character" | "setting"; index: number } | null;
  /** Portraits / scene art are rendering (during the build or the commit). */
  renderingImages?: boolean;
  onUpdateCharacter: (index: number, patch: Partial<ProposedCharacter>) => void;
  onRemoveCharacter: (index: number) => void;
  onUpdateSetting: (index: number, patch: Partial<ProposedSetting>) => void;
  onRemoveSetting: (index: number) => void;
  onDiscard: () => void;
  imagesAvailable: boolean;
  generateImages: boolean;
  onToggleImages: (value: boolean) => void;
}) {
  const chars = proposed?.characters ?? [];
  const settings = proposed?.settings ?? [];
  const stats = proposed?.stats ?? [];
  // Concepts beyond what's drafted so far → "drafting…" skeletons (build only).
  const pendingChars = building ? (planConcepts?.characters ?? []).slice(chars.length) : [];
  const pendingSettings = building ? (planConcepts?.settings ?? []).slice(settings.length) : [];
  const empty = chars.length + settings.length + pendingChars.length + pendingSettings.length === 0;

  return (
    // Contained right pane (mirrors TriagePanel): fixed-width column at md+, bounded
    // strip below md; sticky header + independently scrolling body.
    <section
      aria-label={building ? "World being built" : "Proposed world"}
      className="flex min-h-0 max-h-[42dvh] shrink-0 flex-col border-t border-hair-strong bg-card md:max-h-none md:w-[360px] md:border-t-0 md:border-l md:self-stretch"
    >
      {/* ── Sticky top: stage / summary + controls ──────────────────────── */}
      <div className="sticky top-0 z-10 flex flex-col gap-[10px] border-b border-hair-strong bg-card p-[18px_20px]">
        <div className="flex items-center justify-between gap-[8px]">
          <Eyebrow size={10} tracking="0.2em" color="#A8762A">
            ❖ {building ? "Building the world" : "Proposed world"}
          </Eyebrow>
          {!building && proposed ? (
            <button
              type="button"
              onClick={onDiscard}
              className="cursor-pointer font-mono text-[10px] tracking-[0.08em] text-mute uppercase hover:text-danger"
            >
              Discard
            </button>
          ) : null}
        </div>

        {building ? (
          <p aria-live="polite" className="font-body text-[13px] text-mute">
            {buildStage ?? "Drafting the world…"}
          </p>
        ) : proposed ? (
          <>
            <p className="font-mono text-[10px] tracking-[0.04em] text-mute2">
              {chars.length} character{chars.length === 1 ? "" : "s"} · {settings.length} setting
              {settings.length === 1 ? "" : "s"} · {stats.length} stat{stats.length === 1 ? "" : "s"}.
              Title / genre / primer / stats are editable on the left.
            </p>
            {imagesAvailable ? (
              <label className="inline-flex cursor-pointer items-center gap-[8px]">
                <input
                  type="checkbox"
                  checked={generateImages}
                  onChange={(e) => onToggleImages(e.target.checked)}
                  className="h-[15px] w-[15px] accent-[var(--accent)]"
                />
                <span className="font-body text-[12.5px] text-ink">
                  Generate portraits &amp; scene art{" "}
                  <span className="text-mute2">(ComfyUI · rendered during the build)</span>
                </span>
              </label>
            ) : (
              <p className="font-body text-[12px] text-mute">
                Configure ComfyUI in Options to render portraits &amp; scene art on create.
              </p>
            )}
          </>
        ) : null}
      </div>

      {/* ── Scrollable body: cast + settings ─────────────────────────────── */}
      <div className="flex min-h-0 flex-1 flex-col gap-[16px] overflow-y-auto p-[18px_20px] pt-[16px]">
        {empty ? (
          <p className="font-body text-[13px] text-ink-soft">
            The cast and settings will appear here as Velora drafts them.
          </p>
        ) : null}

        {chars.length + pendingChars.length > 0 ? (
          <div>
            <Eyebrow tracking="0.14em" color="#A8762A" className="mb-[8px] block">
              Characters
            </Eyebrow>
            <ul className="flex flex-col gap-[8px]">
              {chars.map((c, i) => (
                <CharacterCard
                  key={i}
                  c={c}
                  index={i}
                  building={building}
                  committing={renderingImages}
                  active={
                    building &&
                    activeEntity?.type === "character" &&
                    activeEntity.index === i
                  }
                  onUpdate={onUpdateCharacter}
                  onRemove={onRemoveCharacter}
                />
              ))}
              {pendingChars.map((concept, i) => (
                <PendingCard key={`pc-${i}`} concept={concept} />
              ))}
            </ul>
          </div>
        ) : null}

        {settings.length + pendingSettings.length > 0 ? (
          <div>
            <Eyebrow tracking="0.14em" color="#A8762A" className="mb-[8px] block">
              Settings
            </Eyebrow>
            <ul className="flex flex-col gap-[8px]">
              {settings.map((s, i) => (
                <SettingCard
                  key={i}
                  s={s}
                  index={i}
                  building={building}
                  committing={renderingImages}
                  active={
                    building &&
                    activeEntity?.type === "setting" &&
                    activeEntity.index === i
                  }
                  onUpdate={onUpdateSetting}
                  onRemove={onRemoveSetting}
                />
              ))}
              {pendingSettings.map((concept, i) => (
                <PendingCard key={`ps-${i}`} concept={concept} />
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </section>
  );
}

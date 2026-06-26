"use client";

import { Eyebrow } from "@/components/ui/Eyebrow";
import { TextField } from "@/components/ui/TextField";
import type { ProposedCharacter, ProposedSetting, ProposedWorld } from "@/lib/types";

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

/**
 * Review panel for an agentic world build (`ProposedWorld`): the cast and settings
 * that will be created on commit, each editable (name) and prunable. The storyline
 * core + stats are reflected into — and edited from — the page's left column.
 */
export function ProposedWorldReview({
  proposed,
  onUpdateCharacter,
  onRemoveCharacter,
  onUpdateSetting,
  onRemoveSetting,
  onDiscard,
  imagesAvailable,
  generateImages,
  onToggleImages,
}: {
  proposed: ProposedWorld;
  onUpdateCharacter: (index: number, patch: Partial<ProposedCharacter>) => void;
  onRemoveCharacter: (index: number) => void;
  onUpdateSetting: (index: number, patch: Partial<ProposedSetting>) => void;
  onRemoveSetting: (index: number) => void;
  onDiscard: () => void;
  /** Whether ComfyUI is configured (the image toggle only shows when true). */
  imagesAvailable: boolean;
  generateImages: boolean;
  onToggleImages: (value: boolean) => void;
}) {
  const { stats, characters, settings } = proposed;
  return (
    <section
      aria-label="Proposed world"
      className="rounded-[5px] border border-accent/40 bg-card p-[18px_20px]"
    >
      <div className="flex flex-wrap items-center justify-between gap-[10px]">
        <div>
          <Eyebrow size={9} tracking="0.2em" color="#A8762A">
            ❖ Proposed world — review before creating
          </Eyebrow>
          <p className="mt-[4px] font-mono text-[10px] tracking-[0.04em] text-mute2">
            {characters.length} character{characters.length === 1 ? "" : "s"} ·{" "}
            {settings.length} setting{settings.length === 1 ? "" : "s"} · {stats.length} stat
            {stats.length === 1 ? "" : "s"}. Title / genre / primer / stats are editable on the
            left.
          </p>
        </div>
        <button
          type="button"
          onClick={onDiscard}
          className="cursor-pointer font-mono text-[10px] tracking-[0.08em] text-mute uppercase hover:text-danger"
        >
          Discard proposal
        </button>
      </div>

      {stats.length > 0 ? (
        <p className="mt-[12px] font-body text-[12.5px] text-ink-soft">
          <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-mute2">
            Statistics:{" "}
          </span>
          {stats.map((s) => s.displayName).join(" · ")}
        </p>
      ) : null}

      {/* Opt-in image generation (only when ComfyUI is configured). */}
      <div className="mt-[12px]">
        {imagesAvailable ? (
          <label className="inline-flex cursor-pointer items-center gap-[8px]">
            <input
              type="checkbox"
              checked={generateImages}
              onChange={(e) => onToggleImages(e.target.checked)}
              className="h-[15px] w-[15px] accent-[var(--accent)]"
            />
            <span className="font-body text-[13px] text-ink">
              Generate portraits &amp; scene art{" "}
              <span className="text-mute2">(ComfyUI · rendered on create)</span>
            </span>
          </label>
        ) : (
          <p className="font-body text-[12px] text-mute">
            Configure ComfyUI in Options to render portraits &amp; scene art on create.
          </p>
        )}
      </div>

      <div className="mt-[14px] grid grid-cols-1 gap-[16px] lg:grid-cols-2">
        <div>
          <Eyebrow size={9} tracking="0.14em" color="#A8762A" className="mb-[8px] block">
            Characters
          </Eyebrow>
          <ul className="flex flex-col gap-[8px]">
            {characters.length === 0 ? (
              <li className="font-body text-[12.5px] text-mute">None proposed.</li>
            ) : (
              characters.map((c, i) => (
                <li
                  key={i}
                  className="rounded-[4px] border border-cardbd bg-field px-[10px] py-[9px]"
                >
                  <div className="flex items-start gap-[8px]">
                    <div className="min-w-0 flex-1">
                      <TextField
                        aria-label={`Character ${i + 1} name`}
                        value={c.name}
                        onChange={(e) => onUpdateCharacter(i, { name: e.target.value })}
                      />
                      <p className="mt-[5px] font-mono text-[10px] tracking-[0.04em] text-mute2">
                        {c.role}
                        {c.traits ? ` · ${c.traits}` : ""}
                      </p>
                    </div>
                    <RemoveButton label={`Remove ${c.name}`} onClick={() => onRemoveCharacter(i)} />
                  </div>
                </li>
              ))
            )}
          </ul>
        </div>

        <div>
          <Eyebrow size={9} tracking="0.14em" color="#A8762A" className="mb-[8px] block">
            Settings
          </Eyebrow>
          <ul className="flex flex-col gap-[8px]">
            {settings.length === 0 ? (
              <li className="font-body text-[12.5px] text-mute">None proposed.</li>
            ) : (
              settings.map((s, i) => (
                <li
                  key={i}
                  className="rounded-[4px] border border-cardbd bg-field px-[10px] py-[9px]"
                >
                  <div className="flex items-start gap-[8px]">
                    <div className="min-w-0 flex-1">
                      <TextField
                        aria-label={`Setting ${i + 1} name`}
                        value={s.name}
                        onChange={(e) => onUpdateSetting(i, { name: e.target.value })}
                      />
                      <p className="mt-[5px] font-mono text-[10px] tracking-[0.04em] text-mute2">
                        {s.type}
                        {s.desc ? ` · ${s.desc}` : ""}
                      </p>
                    </div>
                    <RemoveButton label={`Remove ${s.name}`} onClick={() => onRemoveSetting(i)} />
                  </div>
                </li>
              ))
            )}
          </ul>
        </div>
      </div>
    </section>
  );
}

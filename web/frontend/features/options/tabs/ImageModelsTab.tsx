"use client";

import { useState } from "react";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { TextField } from "@/components/ui/TextField";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import {
  checkComfyStatus,
  fetchComfyLoras,
  fetchComfyWorkflows,
  type ArtStyleId,
  type ArtStyleOverride,
  type ArtStyleRead,
  type ComfyParams,
} from "@/lib/api";
import type { OptionsState } from "@/features/options/useOptionsSettings";

const PARAM_FIELDS: { key: keyof Omit<ComfyParams, "negativePrompt">; label: string; step: number; min: number; max: number }[] = [
  { key: "steps", label: "Steps", step: 1, min: 1, max: 150 },
  { key: "cfg", label: "CFG", step: 0.1, min: 0, max: 30 },
  { key: "width", label: "Width", step: 8, min: 64, max: 4096 },
  { key: "height", label: "Height", step: 8, min: 64, max: 4096 },
  { key: "batchSize", label: "Batch size", step: 1, min: 1, max: 16 },
];

const DEFAULT_PARAMS: ComfyParams = {
  steps: 4,
  cfg: 1,
  width: 1024,
  height: 1024,
  batchSize: 1,
  negativePrompt: "",
};

/**
 * The Image Generation tab: configure a local ComfyUI server, pick a saved
 * workflow (`GET /options/comfy/workflows`), tune default generation params, choose the
 * **default art style** and each style's LoRA, run a live status check
 * (`POST /options/comfy/status`), and save to the backend.
 * Mirrors `LanguageModelsTab`'s lazy-init + keyed-remount pattern.
 *
 * The per-style LoRA rows are what make the style catalog operator-owned rather than
 * hard-coded: `anime` ships with no LoRA because none is installed, and pointing it at one
 * later is a change here, not a change in the backend. A style with its LoRA off renders on
 * the base checkpoint — the workflow's LoRA node is bypassed rather than retuned.
 */
export function ImageModelsTab({ opts }: { opts: OptionsState }) {
  const comfy = opts.settings?.comfy;
  const [baseUrl, setBaseUrl] = useState(comfy?.baseUrl ?? "");
  const [workflow, setWorkflow] = useState(comfy?.workflow ?? "");
  const [params, setParams] = useState<ComfyParams>(comfy?.params ?? DEFAULT_PARAMS);
  const [artStyle, setArtStyle] = useState<ArtStyleId>(comfy?.artStyle ?? "painted");
  // Keyed by style id, seeded from the effective values the backend returned.
  const [styleLoras, setStyleLoras] = useState<Record<string, ArtStyleOverride>>(() =>
    Object.fromEntries(
      (comfy?.styles ?? []).map((s: ArtStyleRead) => [
        s.id,
        { loraName: s.loraName, loraStrength: s.loraStrength, loraEnabled: s.loraEnabled },
      ]),
    ),
  );
  const [loras, setLoras] = useState<string[]>([]);

  const [workflows, setWorkflows] = useState<string[]>([]);
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const [checking, setChecking] = useState(false);
  const [statusResult, setStatusResult] = useState<string | null>(null);
  const [statusOk, setStatusOk] = useState<boolean | null>(null);

  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!comfy) {
    return <p className="font-body text-body-sm text-mute">Loading image-generation settings…</p>;
  }

  async function loadWorkflows() {
    setFetching(true);
    setFetchError(null);
    try {
      const { workflows: found } = await fetchComfyWorkflows();
      setWorkflows(found);
      if (found.length === 0) setFetchError("No workflows found in utils/workflows/.");
    } catch (err) {
      setWorkflows([]);
      setFetchError(err instanceof Error ? err.message : "Could not list workflows.");
    } finally {
      setFetching(false);
    }
  }

  function patchStyle(id: string, patch: ArtStyleOverride) {
    setStyleLoras((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }

  async function loadLoras() {
    try {
      setLoras((await fetchComfyLoras()).loras);
    } catch {
      // Best-effort: the field stays free text. See the component docstring.
      setLoras([]);
    }
  }

  async function runStatus() {
    if (!baseUrl.trim()) return;
    setChecking(true);
    setStatusResult(null);
    setStatusOk(null);
    try {
      const res = await checkComfyStatus({ baseUrl });
      setStatusOk(res.ok);
      const bits = [
        res.comfyuiVersion ? `v${res.comfyuiVersion}` : null,
        res.device || null,
      ].filter(Boolean);
      setStatusResult(`OK${bits.length ? ` · ${bits.join(" · ")}` : ""}`);
    } catch (err) {
      setStatusOk(false);
      setStatusResult(err instanceof Error ? err.message : "Status check failed.");
    } finally {
      setChecking(false);
    }
  }

  async function save() {
    setSaving(true);
    setStatus(null);
    try {
      await opts.saveComfy({ baseUrl, workflow, params, artStyle, styles: styleLoras });
      setStatus("Saved.");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  // Keep the stored/typed workflow selectable even if the list hasn't loaded.
  const workflowOptions = workflow && !workflows.includes(workflow) ? [workflow, ...workflows] : workflows;

  return (
    <section aria-labelledby="images-heading">
      <h2 id="images-heading" className="font-display text-step-1 font-semibold text-ink">
        Image generation
      </h2>
      <p className="mt-2xs mb-lg font-body text-body-sm text-ink-soft">
        Point Mytheca at a local ComfyUI server. Workflows are loaded from{" "}
        <code className="font-mono text-eyebrow text-ink">utils/workflows/</code>.
      </p>

      <div className="grid gap-lg">
        <div className="flex items-end gap-sm">
          <TextField
            label="ComfyUI base URL"
            className="flex-1"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://localhost:8199"
            inputMode="url"
          />
          <Button variant="ghost" onClick={() => void runStatus()} disabled={checking || !baseUrl.trim()}>
            {checking ? "Checking…" : "Check status"}
          </Button>
        </div>
        {statusResult ? (
          <p
            aria-live="polite"
            className={`-mt-sm font-mono text-eyebrow tracking-[0.04em] ${statusOk ? "text-success-ink" : "text-danger-ink"}`}
          >
            {statusResult}
          </p>
        ) : null}

        <div className="flex items-end gap-sm">
          <label className="block flex-1">
            <FieldLabel>
              Workflow {workflows.length > 0 ? `(${workflows.length} available)` : ""}
            </FieldLabel>
            {workflows.length > 0 ? (
              <select
                value={workflow}
                onChange={(e) => setWorkflow(e.target.value)}
                className="w-full rounded-xs border border-field-bd bg-field px-md py-sm font-body text-field text-ink focus:border-accent focus:outline-none"
              >
                <option value="">Select a workflow…</option>
                {workflowOptions.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
            ) : (
              <input
                value={workflow}
                onChange={(e) => setWorkflow(e.target.value)}
                placeholder="List workflows, or type a file name"
                className="w-full rounded-xs border border-field-bd bg-field px-md py-sm font-body text-field text-ink focus:border-accent focus:outline-none"
              />
            )}
          </label>
          <Button variant="secondary" onClick={() => void loadWorkflows()} disabled={fetching}>
            {fetching ? "Loading…" : "List workflows"}
          </Button>
        </div>
        {fetchError ? (
          <p role="alert" className="-mt-sm font-mono text-eyebrow tracking-[0.04em] text-danger-ink">
            {fetchError}
          </p>
        ) : null}

        <fieldset className="rounded-sm border border-cardbd p-lg">
          <legend className="px-xs font-mono text-eyebrow tracking-[0.14em] text-gold-ink uppercase">
            Default generation parameters
          </legend>
          <div className="grid gap-md sm:grid-cols-2 lg:grid-cols-3">
            {PARAM_FIELDS.map((f) => (
              <TextField
                key={f.key}
                label={f.label}
                type="number"
                step={f.step}
                min={f.min}
                max={f.max}
                value={String(params[f.key])}
                onChange={(e) => setParams((p) => ({ ...p, [f.key]: Number(e.target.value) }))}
              />
            ))}
          </div>
          <label className="mt-md block">
            <FieldLabel>Negative prompt</FieldLabel>
            <input
              value={params.negativePrompt}
              onChange={(e) => setParams((p) => ({ ...p, negativePrompt: e.target.value }))}
              placeholder="low quality, bad anatomy…"
              className="w-full rounded-xs border border-field-bd bg-field px-md py-sm font-body text-field text-ink focus:border-accent focus:outline-none"
            />
          </label>
        </fieldset>

        <fieldset className="rounded-sm border border-cardbd p-lg">
          <legend className="px-xs font-mono text-eyebrow tracking-[0.14em] text-gold-ink uppercase">
            Art style
          </legend>
          <p className="mb-sm font-body text-eyebrow text-ink-soft">
            The look every generated image starts from — portraits, place art, scene art, and
            the in-play picture alike. Each surface&apos;s own picker overrides it per render.
          </p>
          <div className="grid gap-sm sm:grid-cols-3">
            {(comfy.styles ?? []).map((style) => (
              <label
                key={style.id}
                className={cn(
                  "flex cursor-pointer flex-col rounded-sm border p-[10px_12px]",
                  "focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent",
                  style.id === artStyle
                    ? "border-[1.5px] border-accent bg-card2"
                    : "border-field-bd bg-field hover:border-hair-strong hover:bg-hover",
                )}
              >
                <span className="flex items-center gap-sm">
                  <input
                    type="radio"
                    name="default-art-style"
                    value={style.id}
                    checked={style.id === artStyle}
                    onChange={() => setArtStyle(style.id)}
                    className="accent-[var(--accent)]"
                  />
                  <span
                    className={cn(
                      "font-body text-body-sm text-ink",
                      style.id === artStyle && "font-semibold text-accent-ink",
                    )}
                  >
                    {style.label}
                  </span>
                </span>
                <span className="mt-3xs font-body text-eyebrow leading-[1.4] text-mute">
                  {style.blurb}
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="rounded-sm border border-cardbd p-lg">
          <legend className="px-xs font-mono text-eyebrow tracking-[0.14em] text-gold-ink uppercase">
            Style LoRAs
          </legend>
          <div className="mb-sm flex flex-wrap items-center justify-between gap-sm">
            <p className="max-w-[46ch] font-body text-eyebrow text-ink-soft">
              Which LoRA each style loads. Turn one off and that style renders on the base
              checkpoint alone — the workflow&apos;s LoRA node is routed around.
            </p>
            <Button variant="secondary" onClick={() => void loadLoras()}>
              {loras.length > 0 ? `List LoRAs (${loras.length})` : "List LoRAs"}
            </Button>
          </div>
          <div className="grid gap-md">
            {(comfy.styles ?? []).map((style) => {
              const entry = styleLoras[style.id] ?? {};
              const name = entry.loraName ?? "";
              const options = name && !loras.includes(name) ? [name, ...loras] : loras;
              return (
                <div
                  key={style.id}
                  className="grid gap-sm sm:grid-cols-[auto_1fr_110px] sm:items-end"
                >
                  <label className="flex items-center gap-sm font-body text-label text-ink">
                    <input
                      type="checkbox"
                      checked={entry.loraEnabled ?? false}
                      onChange={(e) => patchStyle(style.id, { loraEnabled: e.target.checked })}
                      className="accent-[var(--accent)]"
                      aria-label={`Use a LoRA for ${style.label}`}
                    />
                    <span className="min-w-[76px]">{style.label}</span>
                  </label>
                  <label className="block min-w-0">
                    <FieldLabel>{`${style.label} LoRA file`}</FieldLabel>
                    {options.length > 0 ? (
                      <select
                        value={name}
                        onChange={(e) => patchStyle(style.id, { loraName: e.target.value })}
                        className="w-full rounded-xs border border-field-bd bg-field px-md py-sm font-body text-field text-ink focus:border-accent focus:outline-none"
                      >
                        <option value="">None</option>
                        {options.map((l) => (
                          <option key={l} value={l}>
                            {l}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        value={name}
                        onChange={(e) => patchStyle(style.id, { loraName: e.target.value })}
                        placeholder="List LoRAs, or type a file name"
                        className="w-full rounded-xs border border-field-bd bg-field px-md py-sm font-body text-field text-ink focus:border-accent focus:outline-none"
                      />
                    )}
                  </label>
                  <TextField
                    label="Strength"
                    type="number"
                    step={0.05}
                    min={0}
                    max={2}
                    value={String(entry.loraStrength ?? 0.8)}
                    onChange={(e) =>
                      patchStyle(style.id, { loraStrength: Number(e.target.value) })
                    }
                  />
                </div>
              );
            })}
          </div>
        </fieldset>

        <div className="flex flex-wrap items-center gap-md">
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
          {status ? (
            <span aria-live="polite" className="font-mono text-eyebrow tracking-[0.06em] text-ink-soft">
              {status}
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
}

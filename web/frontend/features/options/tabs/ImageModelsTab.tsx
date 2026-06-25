"use client";

import { useState } from "react";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { TextField } from "@/components/ui/TextField";
import { Button } from "@/components/ui/Button";
import { checkComfyStatus, fetchComfyWorkflows, type ComfyParams } from "@/lib/api";
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
 * workflow (`GET /options/comfy/workflows`), tune default generation params, run
 * a live status check (`POST /options/comfy/status`), and save to the backend.
 * Mirrors `LanguageModelsTab`'s lazy-init + keyed-remount pattern.
 */
export function ImageModelsTab({ opts }: { opts: OptionsState }) {
  const comfy = opts.settings?.comfy;
  const [baseUrl, setBaseUrl] = useState(comfy?.baseUrl ?? "");
  const [workflow, setWorkflow] = useState(comfy?.workflow ?? "");
  const [params, setParams] = useState<ComfyParams>(comfy?.params ?? DEFAULT_PARAMS);

  const [workflows, setWorkflows] = useState<string[]>([]);
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const [checking, setChecking] = useState(false);
  const [statusResult, setStatusResult] = useState<string | null>(null);
  const [statusOk, setStatusOk] = useState<boolean | null>(null);

  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!comfy) {
    return <p className="font-body text-[14px] text-mute">Loading image-generation settings…</p>;
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
      await opts.saveComfy({ baseUrl, workflow, params });
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
      <h2 id="images-heading" className="font-display text-[19px] font-semibold text-ink">
        Image generation
      </h2>
      <p className="mt-[4px] mb-[18px] font-body text-[14px] text-ink-soft">
        Point Velora at a local ComfyUI server. Workflows are loaded from{" "}
        <code className="font-mono text-[12px] text-ink">utils/workflows/</code>.
      </p>

      <div className="grid gap-[16px]">
        <div className="flex items-end gap-[10px]">
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
            className={`-mt-[8px] font-mono text-[11px] tracking-[0.04em] ${statusOk ? "text-success" : "text-danger"}`}
          >
            {statusResult}
          </p>
        ) : null}

        <div className="flex items-end gap-[10px]">
          <label className="block flex-1">
            <FieldLabel>
              Workflow {workflows.length > 0 ? `(${workflows.length} available)` : ""}
            </FieldLabel>
            {workflows.length > 0 ? (
              <select
                value={workflow}
                onChange={(e) => setWorkflow(e.target.value)}
                className="w-full rounded-[2px] border border-field-bd bg-field px-[11px] py-[8px] font-body text-[15px] text-ink focus:border-accent focus:outline-none"
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
                className="w-full rounded-[2px] border border-field-bd bg-field px-[11px] py-[8px] font-body text-[15px] text-ink focus:border-accent focus:outline-none"
              />
            )}
          </label>
          <Button variant="secondary" onClick={() => void loadWorkflows()} disabled={fetching}>
            {fetching ? "Loading…" : "List workflows"}
          </Button>
        </div>
        {fetchError ? (
          <p role="alert" className="-mt-[8px] font-mono text-[11px] tracking-[0.04em] text-danger">
            {fetchError}
          </p>
        ) : null}

        <fieldset className="rounded-[4px] border border-cardbd p-[14px]">
          <legend className="px-[6px] font-mono text-[9px] tracking-[0.14em] text-gold uppercase">
            Default generation parameters
          </legend>
          <div className="grid gap-[12px] sm:grid-cols-2 lg:grid-cols-3">
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
          <label className="mt-[12px] block">
            <FieldLabel>Negative prompt</FieldLabel>
            <input
              value={params.negativePrompt}
              onChange={(e) => setParams((p) => ({ ...p, negativePrompt: e.target.value }))}
              placeholder="low quality, bad anatomy…"
              className="w-full rounded-[2px] border border-field-bd bg-field px-[11px] py-[8px] font-body text-[15px] text-ink focus:border-accent focus:outline-none"
            />
          </label>
        </fieldset>

        <div className="flex flex-wrap items-center gap-[12px]">
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
          {status ? (
            <span aria-live="polite" className="font-mono text-[11px] tracking-[0.06em] text-ink-soft">
              {status}
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
}

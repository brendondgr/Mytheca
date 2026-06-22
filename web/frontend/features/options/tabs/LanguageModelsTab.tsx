"use client";

import { useState } from "react";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { TextField } from "@/components/ui/TextField";
import { Button } from "@/components/ui/Button";
import type { LlmParams } from "@/lib/api";
import type { OptionsState } from "@/features/options/useOptionsSettings";

const PARAM_FIELDS: { key: keyof LlmParams; label: string; step: number; min: number; max: number }[] = [
  { key: "temperature", label: "Temperature", step: 0.05, min: 0, max: 2 },
  { key: "maxTokens", label: "Max tokens", step: 1, min: 1, max: 32000 },
  { key: "topP", label: "Top P", step: 0.05, min: 0, max: 1 },
  { key: "frequencyPenalty", label: "Frequency penalty", step: 0.1, min: -2, max: 2 },
  { key: "presencePenalty", label: "Presence penalty", step: 0.1, min: -2, max: 2 },
];

/**
 * The Language Models tab: configure an OpenAI-compatible endpoint (base URL,
 * API key, model, generation params) and save it to the backend store. Model
 * discovery + a live connection test are added in the next step.
 */
export function LanguageModelsTab({ opts }: { opts: OptionsState }) {
  const llm = opts.settings?.llm;
  // Lazy-init from the loaded config. OptionsView keys this component on whether
  // settings are loaded, so it remounts with the correct values (no hydration
  // effect, no synchronous setState-in-effect).
  const [baseUrl, setBaseUrl] = useState(llm?.baseUrl ?? "");
  const [model, setModel] = useState(llm?.model ?? "");
  const [apiKey, setApiKey] = useState("");
  const [params, setParams] = useState<LlmParams>(
    llm?.params ?? {
      temperature: 0.7,
      maxTokens: 512,
      topP: 1,
      frequencyPenalty: 0,
      presencePenalty: 0,
    },
  );
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!llm) {
    return <p className="font-body text-[14px] text-mute">Loading language-model settings…</p>;
  }

  async function save() {
    setSaving(true);
    setStatus(null);
    try {
      // Only send apiKey when the user typed one (blank = keep the stored key).
      await opts.saveLlm({
        baseUrl,
        model,
        params,
        ...(apiKey ? { apiKey } : {}),
      });
      setApiKey("");
      setStatus("Saved.");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="models-heading">
      <h2 id="models-heading" className="font-display text-[19px] font-semibold text-ink">
        Language models
      </h2>
      <p className="mt-[4px] mb-[18px] font-body text-[14px] text-ink-soft">
        Point Velora at any OpenAI-compatible endpoint — a local server or a hosted API.
      </p>

      <div className="grid gap-[16px]">
        <TextField
          label="Base URL"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="http://localhost:7070/v1"
          inputMode="url"
        />

        <label className="block">
          <FieldLabel>API key {llm.hasApiKey ? `(stored: ${llm.apiKeyHint})` : "(optional)"}</FieldLabel>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={llm.hasApiKey ? "•••• leave blank to keep" : "sk-…"}
            autoComplete="off"
            className="w-full rounded-[2px] border border-field-bd bg-field px-[11px] py-[8px] font-body text-[15px] text-ink focus:border-accent focus:outline-none"
          />
        </label>

        <TextField
          label="Model"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="e.g. llama-3.1-8b-instruct"
        />

        <fieldset className="rounded-[4px] border border-cardbd p-[14px]">
          <legend className="px-[6px] font-mono text-[9px] tracking-[0.14em] text-gold uppercase">
            Generation parameters
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
                onChange={(e) =>
                  setParams((p) => ({ ...p, [f.key]: Number(e.target.value) }))
                }
              />
            ))}
          </div>
        </fieldset>

        <div className="flex items-center gap-[12px]">
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

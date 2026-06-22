"use client";

import { useState } from "react";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { TextField } from "@/components/ui/TextField";
import { Button } from "@/components/ui/Button";
import { fetchLlmModels, testLlmConnection, type LlmParams } from "@/lib/api";
import type { OptionsState } from "@/features/options/useOptionsSettings";

const PARAM_FIELDS: { key: keyof LlmParams; label: string; step: number; min: number; max: number }[] = [
  { key: "temperature", label: "Temperature", step: 0.05, min: 0, max: 2 },
  { key: "maxTokens", label: "Max tokens", step: 1, min: 1, max: 32000 },
  { key: "topP", label: "Top P", step: 0.05, min: 0, max: 1 },
  { key: "frequencyPenalty", label: "Frequency penalty", step: 0.1, min: -2, max: 2 },
  { key: "presencePenalty", label: "Presence penalty", step: 0.1, min: -2, max: 2 },
];

const DEFAULT_PARAMS: LlmParams = {
  temperature: 0.7,
  maxTokens: 512,
  topP: 1,
  frequencyPenalty: 0,
  presencePenalty: 0,
};

/**
 * The Language Models tab: configure an OpenAI-compatible endpoint, discover its
 * models (`POST /options/llm/models`), pick one, tune generation params, run a
 * live connection test (`POST /options/llm/test`), and save it to the backend.
 */
export function LanguageModelsTab({ opts }: { opts: OptionsState }) {
  const llm = opts.settings?.llm;
  // Lazy-init from the loaded config. OptionsView keys this component on whether
  // settings are loaded, so it remounts with the correct values (no hydration
  // effect, no synchronous setState-in-effect).
  const [baseUrl, setBaseUrl] = useState(llm?.baseUrl ?? "");
  const [model, setModel] = useState(llm?.model ?? "");
  const [apiKey, setApiKey] = useState("");
  const [params, setParams] = useState<LlmParams>(llm?.params ?? DEFAULT_PARAMS);

  const [models, setModels] = useState<string[]>([]);
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testOk, setTestOk] = useState<boolean | null>(null);

  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!llm) {
    return <p className="font-body text-[14px] text-mute">Loading language-model settings…</p>;
  }

  // Pass apiKey only when the user typed one; the backend falls back to the stored key.
  const credentials = () => ({ baseUrl, ...(apiKey ? { apiKey } : {}) });

  async function fetchModels() {
    if (!baseUrl.trim()) return;
    setFetching(true);
    setFetchError(null);
    try {
      const { models: found } = await fetchLlmModels(credentials());
      setModels(found);
      if (found.length === 0) setFetchError("No models reported by this endpoint.");
    } catch (err) {
      setModels([]);
      setFetchError(err instanceof Error ? err.message : "Could not reach the endpoint.");
    } finally {
      setFetching(false);
    }
  }

  async function runTest() {
    if (!model) return;
    setTesting(true);
    setTestResult(null);
    setTestOk(null);
    try {
      const res = await testLlmConnection({ ...credentials(), model, params });
      setTestOk(res.ok);
      setTestResult(`OK · ${res.latencyMs}ms${res.sample ? ` · "${res.sample}"` : ""}`);
    } catch (err) {
      setTestOk(false);
      setTestResult(err instanceof Error ? err.message : "Test failed.");
    } finally {
      setTesting(false);
    }
  }

  async function save() {
    setSaving(true);
    setStatus(null);
    try {
      await opts.saveLlm({ baseUrl, model, params, ...(apiKey ? { apiKey } : {}) });
      setApiKey("");
      setStatus("Saved.");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  // Keep the stored/typed model selectable even if it isn't in the fetched list.
  const modelOptions = model && !models.includes(model) ? [model, ...models] : models;

  return (
    <section aria-labelledby="models-heading">
      <h2 id="models-heading" className="font-display text-[19px] font-semibold text-ink">
        Language models
      </h2>
      <p className="mt-[4px] mb-[18px] font-body text-[14px] text-ink-soft">
        Point Velora at any OpenAI-compatible endpoint — a local server or a hosted API.
      </p>

      <div className="grid gap-[16px]">
        <div className="flex items-end gap-[10px]">
          <TextField
            label="Base URL"
            className="flex-1"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            onBlur={() => void fetchModels()}
            placeholder="http://localhost:7070/v1"
            inputMode="url"
          />
          <Button variant="secondary" onClick={() => void fetchModels()} disabled={fetching || !baseUrl.trim()}>
            {fetching ? "Fetching…" : "Fetch models"}
          </Button>
        </div>
        {fetchError ? (
          <p role="alert" className="-mt-[8px] font-mono text-[11px] tracking-[0.04em] text-danger">
            {fetchError}
          </p>
        ) : null}

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

        <label className="block">
          <FieldLabel>
            Model {models.length > 0 ? `(${models.length} available)` : ""}
          </FieldLabel>
          {models.length > 0 ? (
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full rounded-[2px] border border-field-bd bg-field px-[11px] py-[8px] font-body text-[15px] text-ink focus:border-accent focus:outline-none"
            >
              <option value="">Select a model…</option>
              {modelOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="Fetch models to choose, or type an id"
              className="w-full rounded-[2px] border border-field-bd bg-field px-[11px] py-[8px] font-body text-[15px] text-ink focus:border-accent focus:outline-none"
            />
          )}
        </label>

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
                onChange={(e) => setParams((p) => ({ ...p, [f.key]: Number(e.target.value) }))}
              />
            ))}
          </div>
        </fieldset>

        <div className="flex flex-wrap items-center gap-[12px]">
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button variant="ghost" onClick={() => void runTest()} disabled={testing || !model}>
            {testing ? "Testing…" : "Test connection"}
          </Button>
          {status ? (
            <span aria-live="polite" className="font-mono text-[11px] tracking-[0.06em] text-ink-soft">
              {status}
            </span>
          ) : null}
          {testResult ? (
            <span
              aria-live="polite"
              className={`font-mono text-[11px] tracking-[0.04em] ${testOk ? "text-success" : "text-danger"}`}
            >
              {testResult}
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
}

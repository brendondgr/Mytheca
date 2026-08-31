"use client";

import { useState } from "react";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { TextField } from "@/components/ui/TextField";
import { Button } from "@/components/ui/Button";
import {
  fetchLlmModels,
  testLlmConnection,
  type LlmParams,
  type ReasoningVisibility,
} from "@/lib/api";
import type { OptionsState } from "@/features/options/useOptionsSettings";

const PARAM_FIELDS: { key: keyof LlmParams; label: string; step: number; min: number; max: number }[] = [
  { key: "temperature", label: "Temperature", step: 0.05, min: 0, max: 2 },
  { key: "maxTokens", label: "Max tokens", step: 1, min: 1, max: 32000 },
  { key: "topP", label: "Top P", step: 0.05, min: 0, max: 1 },
  { key: "frequencyPenalty", label: "Frequency penalty", step: 0.1, min: -2, max: 2 },
  { key: "presencePenalty", label: "Presence penalty", step: 0.1, min: -2, max: 2 },
];

/** The Reasoning-visibility choices, in increasing order of what they reveal. */
const REASONING_CHOICES: { value: ReasoningVisibility; label: string; hint: string }[] = [
  { value: "hidden", label: "Hidden", hint: "No thinking shown at all." },
  {
    value: "summary",
    label: "Character's thought",
    hint: "The muted in-voice line above what they say, and nothing more.",
  },
  {
    value: "full",
    label: "Full reasoning",
    hint: "Also streams the model's raw deliberation live, under a collapsed “working…” line. This is the default: it starts about half a second in, where prose takes several seconds, so the wait shows something. The trade is that the deliberation often states what a character is about to say before they say it — switch to “Character's thought” if that spoils it for you.",
  },
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
  const [provider, setProvider] = useState(llm?.provider ?? "openai-compatible");
  const [baseUrl, setBaseUrl] = useState(llm?.baseUrl ?? "");
  const [model, setModel] = useState(llm?.model ?? "");
  const [apiKey, setApiKey] = useState("");
  const [params, setParams] = useState<LlmParams>(llm?.params ?? DEFAULT_PARAMS);
  const [authoringConcurrency, setAuthoringConcurrency] = useState(llm?.authoringConcurrency ?? 3);
  const [maxContextTokens, setMaxContextTokens] = useState(llm?.maxContextTokens ?? 16384);
  const [reasoningVisibility, setReasoningVisibility] = useState<ReasoningVisibility>(
    llm?.reasoningVisibility ?? "full",
  );

  const [models, setModels] = useState<string[]>([]);
  const [fetching, setFetching] = useState(false);
  /**
   * The THREE empty states, kept apart on purpose. They look identical (an empty
   * dropdown) and mean completely different things, and collapsing them is how a
   * settings panel ends up telling someone their config is wrong when their GPU
   * box is simply off:
   *   "idle"        nothing asked for yet
   *   "none"        nothing configured to ask
   *   "unreachable" asked, could not connect  (`ok: false`)
   *   "empty"       asked, answered, serving nothing
   *   "ok"          asked, answered, has models
   */
  const [discovery, setDiscovery] = useState<
    "idle" | "none" | "unreachable" | "empty" | "ok"
  >("idle");
  const [fetchError, setFetchError] = useState<string | null>(null);

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testOk, setTestOk] = useState<boolean | null>(null);

  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!llm) {
    return <p className="font-body text-body-sm text-mute">Loading language-model settings…</p>;
  }

  const current = llm.providers?.find((p) => p.id === provider);
  const supportsDiscovery = current?.supportsDiscovery ?? true;

  // Pass apiKey only when the user typed one; the backend falls back to the stored key.
  const credentials = () => ({ provider, baseUrl, ...(apiKey ? { apiKey } : {}) });

  async function fetchModels() {
    if (!baseUrl.trim()) {
      setModels([]);
      setDiscovery("none");
      setFetchError(null);
      return;
    }
    setFetching(true);
    setFetchError(null);
    try {
      // The route answers 200 with `ok: false` for an unreachable endpoint —
      // someone's GPU box being off is not an error in Mytheca — so the
      // interesting case arrives here, not in the catch.
      const res = await fetchLlmModels(credentials());
      setModels(res.models);
      if (!res.ok) {
        setDiscovery("unreachable");
        setFetchError(res.error ?? "Could not reach this endpoint.");
      } else if (res.models.length === 0) {
        setDiscovery("empty");
      } else {
        setDiscovery("ok");
      }
    } catch (err) {
      setModels([]);
      setDiscovery("unreachable");
      setFetchError(err instanceof Error ? err.message : "Could not reach the endpoint.");
    } finally {
      setFetching(false);
    }
  }

  /** Switching provider swaps in that provider's own endpoint and clears stale models. */
  function switchProvider(next: string) {
    const option = llm?.providers?.find((p) => p.id === next);
    setProvider(next);
    setModels([]);
    setDiscovery("idle");
    setFetchError(null);
    setApiKey("");
    // Only prefill an EMPTY field: overwriting a URL the operator typed would
    // lose work, and a provider they have already configured keeps its own.
    setBaseUrl((prev) => (prev.trim() ? prev : option?.defaultBaseUrl ?? ""));
    setModel("");
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
      await opts.saveLlm({
        provider,
        baseUrl,
        model,
        params,
        authoringConcurrency,
        maxContextTokens,
        reasoningVisibility,
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

  // Keep the stored/typed model selectable even if it isn't in the fetched list.
  const modelOptions = model && !models.includes(model) ? [model, ...models] : models;

  return (
    <section aria-labelledby="models-heading">
      <h2 id="models-heading" className="font-display text-step-1 font-semibold text-ink">
        Language models
      </h2>
      <p className="mt-2xs mb-lg font-body text-body-sm text-ink-soft">
        Point Mytheca at a local server or a hosted API. Each provider keeps its own
        endpoint and key, so switching between them does not lose either.
      </p>

      <div className="grid gap-lg">
        <label className="block">
          <FieldLabel>Provider</FieldLabel>
          <select
            value={provider}
            onChange={(e) => switchProvider(e.target.value)}
            className="w-full rounded-xs border border-field-bd bg-field px-md py-sm font-body text-field text-ink focus:border-accent focus:outline-none"
          >
            {(llm.providers ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
                {p.configured ? " · configured" : ""}
                {p.streamingDispatched ? "" : " · no live typing"}
              </option>
            ))}
          </select>
          {current && !current.streamingDispatched ? (
            // Said plainly, because the alternative is finding out mid-scene.
            // An unrecognised stream fails the content-type check and every turn
            // silently degrades to the blocking path — the whole passage landing
            // at once, with no error anywhere.
            <p className="mt-2xs font-mono text-eyebrow tracking-[0.04em] text-mute">
              Turns from {current.label} arrive as one block rather than typing out:
              the turn loop does not parse this provider&rsquo;s stream yet. Everything
              else works.
            </p>
          ) : null}
        </label>

        <div className="flex flex-wrap items-end gap-sm">
          <TextField
            label="Base URL"
            className="flex-1"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            onBlur={() => void fetchModels()}
            placeholder="http://localhost:7070/v1"
            inputMode="url"
          />
          {supportsDiscovery ? (
            <Button
              variant="secondary"
              onClick={() => void fetchModels()}
              disabled={fetching || !baseUrl.trim()}
            >
              {fetching ? "Fetching…" : "Fetch models"}
            </Button>
          ) : null}
        </div>
        {/* The three empty states, said differently on purpose. An empty dropdown
            means "nothing configured", "your endpoint is down" and "this server
            serves no models" — and telling someone their configuration is wrong
            when their GPU box is simply off is the failure this exists to avoid. */}
        {discovery === "unreachable" ? (
          <p role="alert" className="-mt-sm font-mono text-eyebrow tracking-[0.04em] text-danger-ink">
            Could not reach this endpoint{fetchError ? ` — ${fetchError}` : "."} Nothing is
            wrong with Mytheca; the server may simply be off.
          </p>
        ) : discovery === "empty" ? (
          <p role="status" className="-mt-sm font-mono text-eyebrow tracking-[0.04em] text-mute">
            Reached the endpoint, and it reports no models. Load one, or type an id below.
          </p>
        ) : discovery === "none" ? (
          <p role="status" className="-mt-sm font-mono text-eyebrow tracking-[0.04em] text-mute">
            No endpoint yet — add a base URL to see what it serves.
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
            className="w-full rounded-xs border border-field-bd bg-field px-md py-sm font-body text-field text-ink focus:border-accent focus:outline-none"
          />
        </label>

        <label className="block">
          <FieldLabel>
            Model {models.length > 0 ? `(${models.length} available)` : ""}
            {!supportsDiscovery ? " — this provider does not list models" : ""}
          </FieldLabel>
          {models.length > 0 ? (
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full rounded-xs border border-field-bd bg-field px-md py-sm font-body text-field text-ink focus:border-accent focus:outline-none"
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
              placeholder={
                supportsDiscovery
                  ? "Fetch models to choose, or type an id"
                  : "Type the model id"
              }
              className="w-full rounded-xs border border-field-bd bg-field px-md py-sm font-body text-field text-ink focus:border-accent focus:outline-none"
            />
          )}
        </label>

        <fieldset className="rounded-sm border border-cardbd p-lg">
          <legend className="px-xs font-mono text-eyebrow tracking-[0.14em] text-gold-ink uppercase">
            Generation parameters
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
        </fieldset>

        <fieldset className="rounded-sm border border-cardbd p-lg">
          <legend className="px-xs font-mono text-eyebrow tracking-[0.14em] text-gold-ink uppercase">
            Authoring
          </legend>
          <div className="grid gap-md sm:grid-cols-2 sm:max-w-[460px]">
            <TextField
              label="Max parallel authoring requests"
              type="number"
              step={1}
              min={1}
              max={16}
              value={String(authoringConcurrency)}
              onChange={(e) => setAuthoringConcurrency(Math.max(1, Number(e.target.value) || 1))}
            />
            <TextField
              label="Max context (tokens)"
              type="number"
              step={1024}
              min={1024}
              value={String(maxContextTokens)}
              onChange={(e) =>
                setMaxContextTokens(Math.max(1024, Number(e.target.value) || 16384))
              }
            />
          </div>
          <p className="mt-sm font-body text-eyebrow text-ink-soft">
            How many characters/settings the world build drafts at once (and how many
            entries a RAG re-index embeds at once). A single-slot server (llama.cpp)
            should stay at <span className="font-mono">1</span>; a batching server
            (vLLM) can go higher. Image generation always runs one at a time.
          </p>
          <p className="mt-2xs font-body text-eyebrow text-ink-soft">
            Max context is the fallback used when the engine does not report a context
            window — set it to match your model&apos;s actual context length.
          </p>
        </fieldset>

        <fieldset className="rounded-sm border border-cardbd p-lg">
          <legend className="px-xs font-mono text-eyebrow tracking-[0.14em] text-gold-ink uppercase">
            Reasoning visibility
          </legend>
          <div className="grid gap-sm">
            {REASONING_CHOICES.map((choice) => (
              <label key={choice.value} className="flex items-start gap-sm">
                <input
                  type="radio"
                  name="reasoning-visibility"
                  value={choice.value}
                  checked={reasoningVisibility === choice.value}
                  onChange={() => setReasoningVisibility(choice.value)}
                  className="mt-2xs flex-none accent-[var(--color-accent)]"
                />
                <span className="min-w-0">
                  <span className="font-body text-body-sm text-ink">{choice.label}</span>
                  <span className="block font-body text-eyebrow text-ink-soft">
                    {choice.hint}
                  </span>
                </span>
              </label>
            ))}
          </div>
          <p className="mt-sm font-body text-eyebrow text-ink-soft">
            How much of a turn&apos;s thinking you see while it is being written. Raw
            reasoning is never written to the scene record — it is live only.
          </p>
        </fieldset>

        <div className="flex flex-wrap items-center gap-md">
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button variant="ghost" onClick={() => void runTest()} disabled={testing || !model}>
            {testing ? "Testing…" : "Test connection"}
          </Button>
          {status ? (
            <span aria-live="polite" className="font-mono text-eyebrow tracking-[0.06em] text-ink-soft">
              {status}
            </span>
          ) : null}
          {testResult ? (
            <span
              aria-live="polite"
              className={`font-mono text-eyebrow tracking-[0.04em] ${testOk ? "text-success-ink" : "text-danger-ink"}`}
            >
              {testResult}
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
}

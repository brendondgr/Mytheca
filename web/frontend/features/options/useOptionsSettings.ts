"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getSettings,
  updateComfyConfig,
  updateLibraryDefaults,
  updateLlmConfig,
  updatePromptsConfig,
  type AppSettings,
  type ComfyConfigUpdate,
  type LibraryDefaultsUpdate,
  type LlmConfigUpdate,
  type PromptsConfigUpdate,
} from "@/lib/api";
import { refreshArtStyles } from "@/hooks/use-art-styles";

export interface OptionsState {
  settings: AppSettings | null;
  loading: boolean;
  error: string | null;
  retry: () => void;
  saveLlm: (body: LlmConfigUpdate) => Promise<void>;
  saveLibrary: (body: LibraryDefaultsUpdate) => Promise<void>;
  saveComfy: (body: ComfyConfigUpdate) => Promise<void>;
  savePrompts: (body: PromptsConfigUpdate) => Promise<void>;
}

/**
 * Loads the global settings document once and exposes savers that apply the
 * server's response back into local state (await-then-apply, like the Library).
 */
export function useOptionsSettings(): OptionsState {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  // `loading` defaults to true for the first load; retry() flips it from an
  // event handler — so no synchronous setState lives inside the effect.
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const load = useCallback(async () => {
    try {
      const data = await getSettings();
      setSettings(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not load settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Canonical mount data-fetch: load() sets state only after awaiting the API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load, nonce]);

  const retry = useCallback(() => {
    setLoading(true);
    setError(null);
    setNonce((n) => n + 1);
  }, []);

  const saveLlm = useCallback(async (body: LlmConfigUpdate) => {
    const llm = await updateLlmConfig(body);
    setSettings((prev) => (prev ? { ...prev, llm } : prev));
  }, []);

  const saveLibrary = useCallback(async (body: LibraryDefaultsUpdate) => {
    const library = await updateLibraryDefaults(body);
    setSettings((prev) => (prev ? { ...prev, library } : prev));
  }, []);

  const saveComfy = useCallback(async (body: ComfyConfigUpdate) => {
    const comfy = await updateComfyConfig(body);
    setSettings((prev) => (prev ? { ...prev, comfy } : prev));
    // Every art-style picker in the app reads a process-lifetime cache of this blob, so a
    // new default would otherwise not reach them until a reload.
    refreshArtStyles();
  }, []);

  const savePrompts = useCallback(async (body: PromptsConfigUpdate) => {
    const prompts = await updatePromptsConfig(body);
    setSettings((prev) => (prev ? { ...prev, prompts } : prev));
  }, []);

  return { settings, loading, error, retry, saveLlm, saveLibrary, saveComfy, savePrompts };
}

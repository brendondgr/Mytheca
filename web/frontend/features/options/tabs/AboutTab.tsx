"use client";

import { useEffect, useState } from "react";
import { API_BASE, getHealth, getLlmBackend } from "@/lib/api";
import type { LlmBackendInfo } from "@/lib/api";
import type { OptionsState } from "@/features/options/useOptionsSettings";

const APP_VERSION = "0.0.0";

/** Maps a raw backend identifier to a human-readable label. */
function formatBackendName(backend: string): string {
  if (backend === "vllm") return "vLLM";
  if (backend === "llamacpp") return "llama.cpp";
  return "Unknown";
}

/** Read-only diagnostics. No secrets — the API key is never surfaced here. */
export function AboutTab({ opts }: { opts: OptionsState }) {
  const [health, setHealth] = useState<string>("checking…");
  const [backendInfo, setBackendInfo] = useState<LlmBackendInfo | null | "error">(null);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((h) => {
        if (!cancelled) setHealth(h.status === "ok" ? "ok" : h.status);
      })
      .catch(() => {
        if (!cancelled) setHealth("unreachable");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getLlmBackend()
      .then((info) => {
        if (!cancelled) setBackendInfo(info);
      })
      .catch(() => {
        if (!cancelled) setBackendInfo("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const llm = opts.settings?.llm;

  const engineValue =
    backendInfo === null
      ? "loading…"
      : backendInfo === "error"
        ? "unavailable"
        : formatBackendName(backendInfo.backend);

  const rows: { label: string; value: string }[] = [
    { label: "App version", value: APP_VERSION },
    { label: "Backend health", value: health },
    { label: "API base", value: API_BASE },
    { label: "LLM provider", value: llm?.provider || "—" },
    { label: "Active model", value: llm?.model || "not set" },
    { label: "Endpoint", value: llm?.baseUrl || "not set" },
    { label: "API key", value: llm?.hasApiKey ? `set (${llm.apiKeyHint})` : "not set" },
    { label: "Inference engine", value: engineValue },
  ];

  /** Sorted budget entries from the detected backend, e.g. low→max. */
  const budgetOrder = ["low", "medium", "high", "very_high", "max"];
  const budgetEntries: { key: string; tokens: number }[] =
    backendInfo !== null && backendInfo !== "error"
      ? budgetOrder
          .filter((k) => k in backendInfo.budgets)
          .map((k) => ({ key: k, tokens: backendInfo.budgets[k] }))
      : [];

  return (
    <section aria-labelledby="about-heading">
      <h2 id="about-heading" className="font-display text-[19px] font-semibold text-ink">
        About &amp; diagnostics
      </h2>
      <p className="mt-[4px] mb-[18px] font-body text-[14px] text-ink-soft">
        A read-only snapshot of the running stack. No secrets are shown.
      </p>

      <dl className="divide-y divide-hair rounded-[4px] border border-cardbd">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-[12px] px-[14px] py-[10px]">
            <dt className="font-mono text-[10px] tracking-[0.12em] text-mute uppercase">
              {row.label}
            </dt>
            <dd className="truncate font-body text-[14px] text-ink" title={row.value}>
              {row.value}
            </dd>
          </div>
        ))}

        {/* Reasoning-budget ladder — only when backend info is available */}
        {budgetEntries.length > 0 ? (
          <div className="px-[14px] py-[10px]">
            <dt className="mb-[8px] font-mono text-[10px] tracking-[0.12em] text-mute uppercase">
              Reasoning budgets
            </dt>
            <dd>
              <ul
                aria-label="Reasoning budget ladder"
                className="flex flex-wrap gap-x-[16px] gap-y-[4px]"
              >
                {budgetEntries.map(({ key, tokens }) => (
                  <li key={key} className="flex items-baseline gap-[4px]">
                    <span className="font-mono text-[10px] tracking-[0.08em] text-mute uppercase">
                      {key.replace("_", " ")}
                    </span>
                    <span className="font-body text-[13px] text-ink">
                      {tokens.toLocaleString()}
                    </span>
                  </li>
                ))}
              </ul>
            </dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}

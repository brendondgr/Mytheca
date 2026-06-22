"use client";

import { useEffect, useState } from "react";
import { API_BASE, getHealth } from "@/lib/api";
import type { OptionsState } from "@/features/options/useOptionsSettings";

const APP_VERSION = "0.0.0";

/** Read-only diagnostics. No secrets — the API key is never surfaced here. */
export function AboutTab({ opts }: { opts: OptionsState }) {
  const [health, setHealth] = useState<string>("checking…");

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

  const llm = opts.settings?.llm;
  const rows: { label: string; value: string }[] = [
    { label: "App version", value: APP_VERSION },
    { label: "Backend health", value: health },
    { label: "API base", value: API_BASE },
    { label: "LLM provider", value: llm?.provider || "—" },
    { label: "Active model", value: llm?.model || "not set" },
    { label: "Endpoint", value: llm?.baseUrl || "not set" },
    { label: "API key", value: llm?.hasApiKey ? `set (${llm.apiKeyHint})` : "not set" },
  ];

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
      </dl>
    </section>
  );
}

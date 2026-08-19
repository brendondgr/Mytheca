"use client";

import { useEffect, useRef, useState } from "react";
import {
  API_BASE,
  cleanupMediaOrphans,
  getHealth,
  getLlmBackend,
  getMediaOrphans,
} from "@/lib/api";
import type { LlmBackendInfo, MediaOrphansResult } from "@/lib/api";
import type { OptionsState } from "@/features/options/useOptionsSettings";

const APP_VERSION = "0.0.0";

/** Maps a raw backend identifier to a human-readable label. */
function formatBackendName(backend: string): string {
  if (backend === "vllm") return "vLLM";
  if (backend === "llamacpp") return "llama.cpp";
  if (backend === "relay") return "OpenAI-protocol relay";
  return "Unknown";
}

/**
 * How the thinking budget is reaching the endpoint, in the operator's terms.
 *
 * Worth a row of its own because its absence hid a real defect: an endpoint matching
 * no probe used to receive no budget at all, so every per-operation reasoning effort
 * was discarded and generations ran until they timed out. "Not sent" is now only
 * possible if a future backend opts out explicitly.
 */
function formatBudgetDelivery(info: LlmBackendInfo): string {
  if (info.budgetApplied === false) return "not sent — the model may think without limit";
  const keys = info.budgetKeys ?? [];
  if (keys.length === 0) return "sent";
  if (keys.length === 1) return `sent as ${keys[0]}`;
  return `sent as ${keys.join(" + ")} (the engine ignores the key it does not know)`;
}

/** Format bytes into a human-readable string (e.g. "1.2 MB"). */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

type ScanState =
  | { phase: "idle" }
  | { phase: "scanning" }
  | { phase: "result"; data: MediaOrphansResult }
  | { phase: "confirming"; data: MediaOrphansResult }
  | { phase: "cleaning" }
  | { phase: "done"; deletedCount: number; freedBytes: number }
  | { phase: "error"; message: string };

/** Read-only diagnostics. No secrets — the API key is never surfaced here. */
export function AboutTab({ opts }: { opts: OptionsState }) {
  const [health, setHealth] = useState<string>("checking…");
  const [backendInfo, setBackendInfo] = useState<LlmBackendInfo | null | "error">(null);
  const [scanState, setScanState] = useState<ScanState>({ phase: "idle" });
  const liveRef = useRef<HTMLDivElement>(null);

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

  async function handleScan() {
    setScanState({ phase: "scanning" });
    try {
      const data = await getMediaOrphans();
      setScanState({ phase: "result", data });
    } catch {
      setScanState({ phase: "error", message: "Scan failed — could not reach the server." });
    }
  }

  function handleConfirm() {
    if (scanState.phase !== "result") return;
    setScanState({ phase: "confirming", data: scanState.data });
  }

  function handleCancelConfirm() {
    if (scanState.phase !== "confirming") return;
    setScanState({ phase: "result", data: scanState.data });
  }

  async function handleCleanup() {
    setScanState({ phase: "cleaning" });
    try {
      const result = await cleanupMediaOrphans();
      setScanState({
        phase: "done",
        deletedCount: result.deletedCount,
        freedBytes: result.freedBytes,
      });
    } catch {
      setScanState({ phase: "error", message: "Cleanup failed — could not reach the server." });
    }
  }

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
    {
      label: "Thinking budget",
      value:
        backendInfo === null
          ? "loading…"
          : backendInfo === "error"
            ? "unavailable"
            : formatBudgetDelivery(backendInfo),
    },
  ];

  /** Sorted budget entries from the detected backend, e.g. low→max. */
  const budgetOrder = ["low", "medium", "high", "very_high", "max"];
  const budgetEntries: { key: string; tokens: number }[] =
    backendInfo !== null && backendInfo !== "error"
      ? budgetOrder
          .filter((k) => k in backendInfo.budgets)
          .map((k) => ({ key: k, tokens: backendInfo.budgets[k] }))
      : [];

  /* aria-live message derived from scan state */
  const liveMessage =
    scanState.phase === "scanning"
      ? "Scanning for orphaned media files…"
      : scanState.phase === "result"
        ? `Scan complete. ${scanState.data.orphanCount} orphan${scanState.data.orphanCount === 1 ? "" : "s"} found, ${scanState.data.eligibleCount} eligible for deletion (${formatBytes(scanState.data.eligibleBytes)}).`
        : scanState.phase === "confirming"
          ? `Ready to delete ${scanState.data.eligibleCount} file${scanState.data.eligibleCount === 1 ? "" : "s"} (${formatBytes(scanState.data.eligibleBytes)}). Confirm to proceed.`
          : scanState.phase === "cleaning"
            ? "Deleting eligible orphaned files…"
            : scanState.phase === "done"
              ? `Done. Deleted ${scanState.deletedCount} file${scanState.deletedCount === 1 ? "" : "s"}, freed ${formatBytes(scanState.freedBytes)}.`
              : scanState.phase === "error"
                ? `Error: ${scanState.message}`
                : "";

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

      {/* ---- Maintenance ---- */}
      <section aria-labelledby="maintenance-heading" className="mt-[32px]">
        <h2
          id="maintenance-heading"
          className="font-display text-[19px] font-semibold text-ink"
        >
          Maintenance
        </h2>
        <p className="mt-[4px] mb-[18px] font-body text-[14px] text-ink-soft">
          Scan and remove WebP files left behind by cancelled drafts or deleted
          entities. Files generated in the last 24 hours are always kept.
        </p>

        {/* aria-live region announces results to screen readers */}
        <div
          ref={liveRef}
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="sr-only"
        >
          {liveMessage}
        </div>

        <div className="rounded-[4px] border border-cardbd p-[16px]">
          {/* Scan button */}
          <div className="flex flex-wrap items-center gap-[10px]">
            <button
              type="button"
              onClick={handleScan}
              disabled={
                scanState.phase === "scanning" || scanState.phase === "cleaning"
              }
              aria-busy={scanState.phase === "scanning"}
              className="rounded-[4px] border border-cardbd bg-surface px-[14px] py-[8px] font-body text-[13px] text-ink transition hover:bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50"
            >
              {scanState.phase === "scanning" ? "Scanning…" : "Scan for orphaned media"}
            </button>

            {/* Inline results summary */}
            {(scanState.phase === "result" || scanState.phase === "confirming") && (
              <span
                aria-hidden="true"
                className="font-body text-[13px] text-ink-soft"
              >
                {scanState.data.orphanCount === 0
                  ? "No orphans found."
                  : `${scanState.data.orphanCount} orphan${scanState.data.orphanCount === 1 ? "" : "s"} found — ${formatBytes(scanState.data.totalBytes)} total, ${scanState.data.eligibleCount} eligible (${formatBytes(scanState.data.eligibleBytes)}).`}
              </span>
            )}

            {scanState.phase === "done" && (
              <span aria-hidden="true" className="font-body text-[13px] text-ink-soft">
                Deleted {scanState.deletedCount} file
                {scanState.deletedCount === 1 ? "" : "s"},{" "}
                freed {formatBytes(scanState.freedBytes)}.
              </span>
            )}

            {scanState.phase === "error" && (
              <span
                role="alert"
                className="font-body text-[13px] text-danger"
              >
                {scanState.message}
              </span>
            )}
          </div>

          {/* Delete / confirmation flow — only shown when there are eligible orphans */}
          {scanState.phase === "result" && scanState.data.eligibleCount > 0 && (
            <div className="mt-[12px]">
              <button
                type="button"
                onClick={handleConfirm}
                className="rounded-[4px] border border-danger/60 bg-surface px-[14px] py-[8px] font-body text-[13px] text-danger transition hover:bg-danger/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-danger"
              >
                Delete {scanState.data.eligibleCount} file
                {scanState.data.eligibleCount === 1 ? "" : "s"} (
                {formatBytes(scanState.data.eligibleBytes)})
              </button>
            </div>
          )}

          {/* Confirm step — second click required, clearly labelled */}
          {scanState.phase === "confirming" && (
            <div
              role="group"
              aria-label="Confirm media deletion"
              className="mt-[12px] flex flex-wrap items-center gap-[10px] rounded-[4px] border border-danger/40 bg-danger/5 px-[14px] py-[10px]"
            >
              <span className="font-body text-[13px] text-ink">
                This will permanently delete{" "}
                <strong>{scanState.data.eligibleCount}</strong>{" "}
                file{scanState.data.eligibleCount === 1 ? "" : "s"}{" "}
                ({formatBytes(scanState.data.eligibleBytes)}). Are you sure?
              </span>
              <div className="flex gap-[8px]">
                <button
                  type="button"
                  onClick={handleCleanup}
                  className="rounded-[4px] bg-danger px-[14px] py-[8px] font-body text-[13px] text-white transition hover:bg-danger/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-danger"
                >
                  Yes, delete
                </button>
                <button
                  type="button"
                  onClick={handleCancelConfirm}
                  className="rounded-[4px] border border-cardbd bg-surface px-[14px] py-[8px] font-body text-[13px] text-ink transition hover:bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Cleaning in progress */}
          {scanState.phase === "cleaning" && (
            <p
              aria-busy="true"
              className="mt-[12px] font-body text-[13px] text-ink-soft"
            >
              Deleting…
            </p>
          )}
        </div>
      </section>
    </section>
  );
}

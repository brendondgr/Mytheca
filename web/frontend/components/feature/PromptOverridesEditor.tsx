"use client";

import { useMemo, useRef, useState } from "react";
import type { PromptSpec } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/TextArea";
import { cn } from "@/lib/cn";

const CONTRACT_KEY = "character.output_contract";

export interface PromptOverridesEditorProps {
  /** All editable prompts + their metadata/default text (from `/options`). */
  catalog: PromptSpec[];
  /** Current overrides for THIS layer ({key → text}); absent keys inherit. */
  overrides: Record<string, string>;
  /**
   * The effective inherited text per key (the resolved lower layers). Falls back to the
   * catalog default. Used as the "revert" target and the modified/overridden comparison.
   */
  baseline?: Record<string, string>;
  /** Persist the layer's complete override map (only overridden, non-blank keys). */
  onSave: (overrides: Record<string, string>) => Promise<void> | void;
  /** Save-button caption (defaults to "Save prompts"). */
  saveLabel?: string;
  /** Unique prefix so multiple editor instances don't collide on tab ids. */
  idPrefix?: string;
}

/**
 * A sub-tabbed editor for the four writing agents' system prompts. Groups the catalog by
 * agent into upper tabs (Character · Narrator · Director · Planner); each prompt shows its
 * description + an editable textarea prefilled with the current override or the inherited
 * default, plus a "Reset to default" affordance. Reused by the Options › Prompts tab
 * (global), the per-storyline modal, and the per-scenario editor — only the `onSave`
 * target differs.
 */
export function PromptOverridesEditor({
  catalog,
  overrides,
  baseline,
  onSave,
  saveLabel = "Save prompts",
  idPrefix = "prompt",
}: PromptOverridesEditorProps) {
  const agents = useMemo(() => {
    const seen: string[] = [];
    for (const spec of catalog) if (!seen.includes(spec.agent)) seen.push(spec.agent);
    return seen;
  }, [catalog]);

  const effectiveDefault = useMemo(
    () => (key: string) => baseline?.[key] ?? catalog.find((s) => s.key === key)?.default ?? "",
    [baseline, catalog],
  );

  // Every field is prefilled with real text: the override if set, else the inherited value.
  const [draft, setDraft] = useState<Record<string, string>>(() => {
    const next: Record<string, string> = {};
    for (const spec of catalog) next[spec.key] = overrides[spec.key] ?? effectiveDefault(spec.key);
    return next;
  });
  const [active, setActive] = useState(agents[0] ?? "");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: "saved" | "error"; msg: string } | null>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const isModified = (key: string) =>
    (draft[key] ?? "").trim() !== effectiveDefault(key).trim();

  function buildOverrides(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const spec of catalog) {
      const val = draft[spec.key] ?? "";
      if (val.trim() && val.trim() !== effectiveDefault(spec.key).trim()) out[spec.key] = val;
    }
    return out;
  }

  // Dirty when the built override map differs from the layer's incoming overrides.
  const next = buildOverrides();
  const keys = new Set([...Object.keys(next), ...Object.keys(overrides)]);
  const dirty = [...keys].some((k) => next[k] !== overrides[k]);

  async function handleSave() {
    setSaving(true);
    setStatus(null);
    try {
      await onSave(buildOverrides());
      setStatus({ kind: "saved", msg: "Saved." });
    } catch (err) {
      setStatus({ kind: "error", msg: err instanceof Error ? err.message : "Could not save." });
    } finally {
      setSaving(false);
    }
  }

  function onTabKey(event: React.KeyboardEvent, index: number) {
    let next = index;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % agents.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp")
      next = (index - 1 + agents.length) % agents.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = agents.length - 1;
    else return;
    event.preventDefault();
    setActive(agents[next]);
    tabRefs.current[next]?.focus();
  }

  const activeSpecs = catalog.filter((s) => s.agent === active);

  return (
    <div className="flex flex-col gap-[16px]">
      {/* Upper sub-tabs, one per writing agent. */}
      <div
        role="tablist"
        aria-label="Writing agents"
        className="flex flex-wrap gap-[6px] border-b border-hair pb-[10px]"
      >
        {agents.map((agent, index) => {
          const selected = agent === active;
          return (
            <button
              key={agent}
              ref={(el) => {
                tabRefs.current[index] = el;
              }}
              role="tab"
              id={`${idPrefix}-tab-${agent}`}
              aria-selected={selected}
              aria-controls={`${idPrefix}-panel-${agent}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(agent)}
              onKeyDown={(event) => onTabKey(event, index)}
              className={cn(
                "cursor-pointer rounded-[3px] border px-[12px] py-[6px] font-mono text-[11px] tracking-[0.08em] uppercase",
                selected
                  ? "border-accent bg-card2 text-ink"
                  : "border-cardbd bg-card text-ink-soft hover:border-hair-strong hover:bg-hover hover:text-ink",
              )}
            >
              {agent}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`${idPrefix}-panel-${active}`}
        aria-labelledby={`${idPrefix}-tab-${active}`}
        className="flex flex-col gap-[18px]"
      >
        {activeSpecs.map((spec) => (
          <div key={spec.key} className="flex flex-col gap-[6px]">
            <div className="flex items-center justify-between gap-[10px]">
              <span className="font-display text-[14.5px] font-semibold text-ink">
                {spec.label}
                {isModified(spec.key) ? (
                  <span className="ml-[8px] font-mono text-tag tracking-[0.06em] text-accent uppercase">
                    overridden
                  </span>
                ) : null}
              </span>
              <button
                type="button"
                onClick={() =>
                  setDraft((prev) => ({ ...prev, [spec.key]: effectiveDefault(spec.key) }))
                }
                disabled={!isModified(spec.key)}
                className="cursor-pointer font-mono text-[10.5px] tracking-[0.08em] text-mute uppercase hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
              >
                Reset to default
              </button>
            </div>
            <p className="font-body text-[13px] text-ink-soft">{spec.description}</p>
            {spec.key === CONTRACT_KEY ? (
              <p className="font-body text-[12.5px] text-danger">
                Caution: this prompt carries the strict{" "}
                <code className="font-mono">&lt;speaker:&gt;</code> /{" "}
                <code className="font-mono">&lt;type:&gt;</code> tags the engine parses — keep
                that format or character replies may fail to render.
              </p>
            ) : null}
            <TextArea
              aria-label={`${spec.agent} — ${spec.label} prompt`}
              rows={spec.key === CONTRACT_KEY ? 12 : 6}
              value={draft[spec.key] ?? ""}
              onChange={(event) =>
                setDraft((prev) => ({ ...prev, [spec.key]: event.target.value }))
              }
              className="font-mono"
            />
          </div>
        ))}
      </div>

      <div className="flex items-center gap-[12px]">
        <Button onClick={handleSave} disabled={saving || !dirty}>
          {saving ? "Saving…" : saveLabel}
        </Button>
        {status ? (
          <span
            role={status.kind === "error" ? "alert" : "status"}
            className={cn(
              "font-body text-[13px]",
              status.kind === "error" ? "text-danger" : "text-ink-soft",
            )}
          >
            {status.msg}
          </span>
        ) : null}
      </div>
    </div>
  );
}

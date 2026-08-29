"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { ToggleChip } from "@/components/ui/ToggleChip";
import { AGENT_FIELDS } from "@/features/library/storylineAgent";
import type { useStorylineAgent } from "@/features/library/useStorylineAgent";
import type { StatChange, StoryPlan, StyleChange } from "@/lib/types";

/**
 * The **Assistant** — a conversational, scope-aware storyline agent that lives in
 * the creator/editor's right pane. The author checks which fields it may write,
 * chats with it (in-chat memory), and it replies + proposes a reviewable plan.
 * Nothing is written until **Approve**. "New chat" resets the conversation.
 */
export function StorylineAgentPanel({
  agent,
  mode,
}: {
  agent: ReturnType<typeof useStorylineAgent>;
  mode: "create" | "edit";
}) {
  const { scope, setWritable, panel, busy, applying, send, approve, dismissPlan, newChat } = agent;
  const [input, setInput] = useState("");

  function submit() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    void send(text);
  }

  const approveLabel = mode === "edit" ? "Approve & apply" : "Approve & fill form";

  return (
    <aside
      aria-label="Storyline assistant"
      className="flex h-full min-h-0 w-full flex-col bg-card2/40"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-[10px] border-b border-hair-strong px-[16px] py-[12px]">
        <Eyebrow size={9.5} tracking="0.2em" color="#A8762A">
          ❖ Assistant
        </Eyebrow>
        <button
          type="button"
          onClick={newChat}
          className="cursor-pointer font-mono text-[10px] tracking-[0.08em] text-mute uppercase hover:text-accent"
        >
          ↺ New chat
        </button>
      </div>

      {/* Scope selector */}
      <div className="border-b border-hair-strong px-[16px] py-[12px]">
        <p className="mb-[8px] font-mono text-[10px] tracking-[0.1em] text-mute2 uppercase">
          The assistant may edit
        </p>
        <div className="flex flex-wrap gap-[6px]">
          {AGENT_FIELDS.map((f) => (
            <ToggleChip
              key={f.key}
              selected={Boolean(scope[f.key]?.writable)}
              onClick={() => setWritable(f.key)}
              className="text-[12px]"
            >
              {f.label}
            </ToggleChip>
          ))}
        </div>
        <p className="mt-[7px] font-body text-[11.5px] text-mute">
          Unchecked fields are structurally out of reach — the assistant can&rsquo;t change them.
        </p>
      </div>

      {/* Conversation */}
      <div
        role="log"
        aria-live="polite"
        aria-label="Conversation with the assistant"
        className="min-h-0 flex-1 space-y-[10px] overflow-y-auto px-[16px] py-[14px]"
      >
        {panel.messages.length === 0 && !panel.streaming ? (
          <p className="font-body text-[13px] text-mute italic">
            Discuss the storyline, then ask for changes — e.g. &ldquo;tighten the tagline&rdquo; or
            &ldquo;rebalance the stats so Resolve tops out at 80.&rdquo;
          </p>
        ) : null}
        {panel.messages.map((m, i) => (
          <MessageBubble key={i} role={m.role} content={m.content} />
        ))}
        {panel.streaming ? <MessageBubble role="assistant" content={panel.streaming} streaming /> : null}
        {busy && !panel.streaming ? (
          <p className="font-body text-[12px] text-mute italic">Thinking…</p>
        ) : null}
        {panel.error ? (
          <p
            role="alert"
            className="rounded-[4px] border border-danger/40 bg-card px-[10px] py-[7px] font-body text-[12.5px] text-danger"
          >
            {panel.error}
          </p>
        ) : null}
      </div>

      {/* Pending plan (the human gate) */}
      {panel.pendingPlan ? (
        <PlanReview
          plan={panel.pendingPlan}
          approveLabel={approveLabel}
          applying={applying}
          onApprove={() => void approve()}
          onDismiss={dismissPlan}
        />
      ) : null}

      {/* Composer */}
      <div className="border-t border-hair-strong px-[16px] py-[12px]">
        <textarea
          aria-label="Message the assistant"
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Discuss first, then ask for changes…"
          className="w-full resize-none rounded-[3px] border border-field-bd bg-field px-[11px] py-[8px] font-body text-[14px] leading-[1.5] text-ink focus:border-accent focus:outline-none"
        />
        <div className="mt-[8px] flex items-center justify-end">
          <Button onClick={submit} disabled={busy || !input.trim()}>
            {busy ? "Sending…" : "Send →"}
          </Button>
        </div>
      </div>
    </aside>
  );
}

function MessageBubble({
  role,
  content,
  streaming,
}: {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}) {
  const isUser = role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap rounded-[8px] px-[11px] py-[8px] font-body text-[13.5px] leading-[1.5]",
          isUser ? "bg-accent/12 text-ink" : "border border-hair bg-card text-ink-soft",
        )}
      >
        {content}
        {streaming ? <span className="text-mute">▋</span> : null}
      </div>
    </div>
  );
}

function PlanReview({
  plan,
  approveLabel,
  applying,
  onApprove,
  onDismiss,
}: {
  plan: StoryPlan;
  approveLabel: string;
  applying: boolean;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  return (
    <section
      aria-label="Proposed plan"
      className="max-h-[42%] overflow-y-auto border-t border-accent/40 bg-card px-[16px] py-[12px]"
    >
      <p className="mb-[8px] font-mono text-[10px] tracking-[0.12em] text-accent uppercase">
        Proposed changes — review before applying
      </p>
      <div className="space-y-[10px]">
        {plan.changes.map((c) => (
          <div key={c.field} className="rounded-[4px] border border-hair bg-field px-[10px] py-[8px]">
            <p className="font-mono text-[10px] tracking-[0.08em] text-mute2 uppercase">{c.field}</p>
            {c.before ? (
              <p className="mt-[3px] font-body text-[12.5px] text-mute line-through">{c.before}</p>
            ) : null}
            <p className="mt-[2px] font-body text-[13.5px] text-ink">{c.after}</p>
            {c.rationale ? (
              <p className="mt-[4px] font-body text-[11.5px] text-ink-soft italic">{c.rationale}</p>
            ) : null}
          </div>
        ))}
        {plan.statChanges.map((s) => (
          <StatChangeRow key={`${s.changeType}-${s.key}`} change={s} />
        ))}
        {(plan.styleChanges ?? []).map((s) => (
          <StyleChangeRow key={s.block} change={s} />
        ))}
      </div>
      <div className="mt-[12px] flex items-center gap-[10px]">
        <Button onClick={onApprove} disabled={applying}>
          {applying ? "Applying…" : approveLabel}
        </Button>
        <button
          type="button"
          onClick={onDismiss}
          disabled={applying}
          className="cursor-pointer font-mono text-[10px] tracking-[0.08em] text-mute uppercase hover:text-accent disabled:opacity-40"
        >
          Dismiss
        </button>
      </div>
    </section>
  );
}

/** One proposed style-block change. A missing `after` is a removal, and says so. */
function StyleChangeRow({ change }: { change: StyleChange }) {
  const removing = !change.after;
  return (
    <div className="rounded-[4px] border border-hair bg-field px-[10px] py-[8px]">
      <p className="font-mono text-[10px] tracking-[0.08em] text-mute2 uppercase">
        Narrative style · {change.block}
        {removing ? <span className="ml-[6px] text-danger">remove</span> : null}
      </p>
      {change.before ? (
        <p className="mt-[3px] font-body text-[12.5px] text-mute line-through">{change.before}</p>
      ) : null}
      {change.after ? (
        <p className="mt-[2px] font-body text-[13.5px] text-ink">{change.after}</p>
      ) : null}
      {change.rationale ? (
        <p className="mt-[4px] font-body text-[11.5px] text-ink-soft italic">{change.rationale}</p>
      ) : null}
    </div>
  );
}

function StatChangeRow({ change }: { change: StatChange }) {
  const verb = { add: "Add", update: "Update", remove: "Remove" }[change.changeType];
  return (
    <div className="rounded-[4px] border border-hair bg-field px-[10px] py-[8px]">
      <div className="flex items-center gap-[8px]">
        <span className="font-mono text-[10px] tracking-[0.08em] text-mute2 uppercase">
          {verb} stat · {change.key}
        </span>
        {change.schemaAltering ? (
          <span className="rounded-[3px] bg-gold/20 px-[5px] py-[1px] font-mono text-[9px] tracking-[0.06em] text-gold uppercase">
            schema change
          </span>
        ) : null}
      </div>
      {change.after && change.changeType !== "remove" ? (
        <p className="mt-[3px] font-body text-[12.5px] text-ink">
          {change.after.displayName || change.after.key} · range {change.after.min}–{change.after.max},
          default {change.after.default}
        </p>
      ) : null}
      {change.rationale ? (
        <p className="mt-[3px] font-body text-[11.5px] text-ink-soft italic">{change.rationale}</p>
      ) : null}
    </div>
  );
}

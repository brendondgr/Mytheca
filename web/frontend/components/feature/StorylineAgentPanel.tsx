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
      <div className="flex items-center justify-between gap-sm border-b border-hair-strong px-lg py-md">
        <Eyebrow size={9.5} tracking="0.2em" entity="#A8762A">
          ❖ Assistant
        </Eyebrow>
        <button
          type="button"
          onClick={newChat}
          className="cursor-pointer font-mono text-eyebrow tracking-[0.08em] text-mute uppercase hover:text-accent-ink"
        >
          ↺ New chat
        </button>
      </div>

      {/* Scope selector */}
      <div className="border-b border-hair-strong px-lg py-md">
        <p className="mb-sm font-mono text-eyebrow tracking-[0.1em] text-mute2 uppercase">
          The assistant may edit
        </p>
        <div className="flex flex-wrap gap-xs">
          {AGENT_FIELDS.map((f) => (
            <ToggleChip
              key={f.key}
              selected={Boolean(scope[f.key]?.writable)}
              onClick={() => setWritable(f.key)}
              className="text-eyebrow"
            >
              {f.label}
            </ToggleChip>
          ))}
        </div>
        <p className="mt-xs font-body text-eyebrow text-mute">
          Unchecked fields are structurally out of reach — the assistant can&rsquo;t change them.
        </p>
      </div>

      {/* Conversation */}
      <div
        role="log"
        aria-live="polite"
        aria-label="Conversation with the assistant"
        className="min-h-0 flex-1 space-y-sm overflow-y-auto px-lg py-lg"
      >
        {panel.messages.length === 0 && !panel.streaming ? (
          <p className="font-body text-label text-mute italic">
            Discuss the storyline, then ask for changes — e.g. &ldquo;tighten the tagline&rdquo; or
            &ldquo;rebalance the stats so Resolve tops out at 80.&rdquo;
          </p>
        ) : null}
        {panel.messages.map((m, i) => (
          <MessageBubble key={i} role={m.role} content={m.content} />
        ))}
        {panel.streaming ? <MessageBubble role="assistant" content={panel.streaming} streaming /> : null}
        {busy && !panel.streaming ? (
          <p className="font-body text-eyebrow text-mute italic">Thinking…</p>
        ) : null}
        {panel.error ? (
          <p
            role="alert"
            className="rounded-sm border border-danger/40 bg-card px-sm py-xs font-body text-eyebrow text-danger-ink"
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
      <div className="border-t border-hair-strong px-lg py-md">
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
          className="w-full resize-none rounded-xs border border-field-bd bg-field px-md py-sm font-body text-field leading-[1.5] text-ink focus:border-accent focus:outline-none"
        />
        <div className="mt-sm flex items-center justify-end">
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
          "max-w-[85%] whitespace-pre-wrap rounded-md px-md py-sm font-body text-label leading-[1.5]",
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
      className="max-h-[42%] overflow-y-auto border-t border-accent/40 bg-card px-lg py-md"
    >
      <p className="mb-sm font-mono text-eyebrow tracking-[0.12em] text-accent-ink uppercase">
        Proposed changes — review before applying
      </p>
      <div className="space-y-sm">
        {plan.changes.map((c) => (
          <div key={c.field} className="rounded-sm border border-hair bg-field px-sm py-sm">
            <p className="font-mono text-eyebrow tracking-[0.08em] text-mute2 uppercase">{c.field}</p>
            {c.before ? (
              <p className="mt-3xs font-body text-eyebrow text-mute line-through">{c.before}</p>
            ) : null}
            <p className="mt-3xs font-body text-label text-ink">{c.after}</p>
            {c.rationale ? (
              <p className="mt-2xs font-body text-eyebrow text-ink-soft italic">{c.rationale}</p>
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
      <div className="mt-md flex items-center gap-sm">
        <Button onClick={onApprove} disabled={applying}>
          {applying ? "Applying…" : approveLabel}
        </Button>
        <button
          type="button"
          onClick={onDismiss}
          disabled={applying}
          className="cursor-pointer font-mono text-eyebrow tracking-[0.08em] text-mute uppercase hover:text-accent-ink disabled:opacity-40"
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
    <div className="rounded-sm border border-hair bg-field px-sm py-sm">
      <p className="font-mono text-eyebrow tracking-[0.08em] text-mute2 uppercase">
        Narrative style · {change.block}
        {removing ? <span className="ml-xs text-danger-ink">remove</span> : null}
      </p>
      {change.before ? (
        <p className="mt-3xs font-body text-eyebrow text-mute line-through">{change.before}</p>
      ) : null}
      {change.after ? (
        <p className="mt-3xs font-body text-label text-ink">{change.after}</p>
      ) : null}
      {change.rationale ? (
        <p className="mt-2xs font-body text-eyebrow text-ink-soft italic">{change.rationale}</p>
      ) : null}
    </div>
  );
}

function StatChangeRow({ change }: { change: StatChange }) {
  const verb = { add: "Add", update: "Update", remove: "Remove" }[change.changeType];
  return (
    <div className="rounded-sm border border-hair bg-field px-sm py-sm">
      <div className="flex items-center gap-sm">
        <span className="font-mono text-eyebrow tracking-[0.08em] text-mute2 uppercase">
          {verb} stat · {change.key}
        </span>
        {change.schemaAltering ? (
          <span className="rounded-xs bg-gold/20 px-2xs py-3xs font-mono text-eyebrow tracking-[0.06em] text-gold-ink uppercase">
            schema change
          </span>
        ) : null}
      </div>
      {change.after && change.changeType !== "remove" ? (
        <p className="mt-3xs font-body text-eyebrow text-ink">
          {change.after.displayName || change.after.key} · range {change.after.min}–{change.after.max},
          default {change.after.default}
        </p>
      ) : null}
      {change.rationale ? (
        <p className="mt-3xs font-body text-eyebrow text-ink-soft italic">{change.rationale}</p>
      ) : null}
    </div>
  );
}

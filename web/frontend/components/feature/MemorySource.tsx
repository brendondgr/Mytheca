"use client";

import { useCallback, useEffect, useState } from "react";

import { AsyncPanel, type AsyncStatus } from "@/components/ui/AsyncPanel";
import { Icon } from "@/components/ui/Icon";
import { IconButton } from "@/components/ui/IconButton";
import { Modal } from "@/components/ui/Modal";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { getBeatMemory } from "@/lib/api";
import type { BeatMemory, RecalledMemory } from "@/lib/events";

/**
 * "Where did this line come from?" — the per-beat source control.
 *
 * Its job is not debugging. When a character throws a line back from three scenarios ago the
 * player has no way to tell a real callback from the model inventing one, and would be right
 * to suspect the second. This is what makes the memory checkable — and it is also what keeps
 * subjective memory from reading as a defect: told *before* Mara pushes back that she
 * remembers the moment differently, the disagreement reads as character rather than as the
 * app losing track of its own story.
 *
 * It sits opposite `BeatControls` deliberately. That cluster edits, re-rolls, branches and
 * rewinds — everything there changes the record. This only reads it, and a mis-click here
 * should never be able to cost a beat. It is its own tab stop rather than a sixth control
 * inside that toolbar, which keeps the "one tab stop per beat" property the roving tabindex
 * there exists to protect.
 *
 * The fetch is deferred until the panel opens. A transcript holds dozens of beats and the
 * player asks about one at a time, so resolving every beat's provenance up front would be
 * work done for a question nobody asked.
 */
export function MemorySource({
  scenarioId,
  sessionId,
  eventId,
  label,
  onJumpTo,
  disabled = false,
}: {
  scenarioId: string;
  sessionId: string;
  /** The beat being asked about. */
  eventId: string;
  /** Whose beat, for the accessible name — "What Mara was remembering". */
  label: string;
  /**
   * Scroll the transcript to an earlier beat. Only offered for a memory formed in **this**
   * play-through: one from an earlier scenario is real history but is not in this
   * transcript, and a link that silently does nothing is worse than no link.
   */
  onJumpTo?: (eventId: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<BeatMemory | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    setFailed(false);
    setData(null);
    return getBeatMemory(scenarioId, sessionId, eventId)
      .then(setData)
      .catch(() => setFailed(true));
  }, [scenarioId, sessionId, eventId]);

  useEffect(() => {
    if (!open || data || failed) return;
    let cancelled = false;
    getBeatMemory(scenarioId, sessionId, eventId)
      .then((body) => {
        if (!cancelled) setData(body);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [open, data, failed, scenarioId, sessionId, eventId]);

  const jump = useCallback(
    (target: string) => {
      setOpen(false);
      onJumpTo?.(target);
    },
    [onJumpTo],
  );

  const status: AsyncStatus = failed
    ? "error"
    : !data
      ? "loading"
      : data.memories.length === 0
        ? "empty"
        : "success";

  return (
    <>
      <IconButton
        label={`What ${label} was remembering`}
        onClick={() => setOpen(true)}
        disabled={disabled}
        aria-expanded={open}
        // Quiet until the beat is hovered or contains focus, and never `display: none` —
        // exactly the rule `BeatControls` uses, including its touch exception: below `sm`
        // there is no hover to reveal it with, so it stays visible there.
        className="transition-opacity duration-150 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
      >
        <Icon name="memory" size={14} />
      </IconButton>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        ariaLabel={`What ${label} was remembering`}
      >
        <div className="p-md">
          <SectionHeader title="What they were remembering" />
          <AsyncPanel
            status={status}
            label="Beat memory"
            errorTitle="That didn't load"
            errorMessage="The record of what this line was written with could not be read."
            onRetry={() => void load()}
            // An empty result is a real answer, not a failure: most lines are written from
            // the scene in front of the character rather than from anything they carry.
            emptyTitle="Nothing carried over"
            emptyMessage="This line came from the scene itself, not from anything remembered."
          >
            <ul className="mt-sm flex flex-col gap-md">
              {(data?.memories ?? []).map((memory) => (
                <MemoryRow key={memory.id} memory={memory} onJumpTo={jump} />
              ))}
            </ul>
          </AsyncPanel>
        </div>
      </Modal>
    </>
  );
}

function MemoryRow({
  memory,
  onJumpTo,
}: {
  memory: RecalledMemory;
  onJumpTo: (eventId: string) => void;
}) {
  const others = memory.contradictedBy;
  return (
    <li className="flex flex-col gap-2xs">
      <p className="text-sm">
        <span className="font-medium">{memory.characterName}</span> remembers: {memory.gloss}
      </p>
      {memory.quote ? (
        <p className="border-l-2 border-line pl-sm text-sm italic">
          “{memory.quote}”
          {memory.quoteSpeakerName ? (
            <span className="not-italic text-fg-muted"> — {memory.quoteSpeakerName}</span>
          ) : null}
        </p>
      ) : null}
      <p className="text-xs text-fg-muted">
        From <span className="italic">{memory.scenarioTitle}</span>
        {memory.inThisSession && memory.eventId ? (
          <>
            {" · "}
            <button
              type="button"
              className="cursor-pointer underline underline-offset-2 hover:opacity-80"
              onClick={() => onJumpTo(memory.eventId!)}
            >
              jump to it
            </button>
          </>
        ) : null}
      </p>
      {others.length > 0 ? (
        // Surfaced before it can read as a bug. A cast that remembers subjectively WILL
        // produce characters who flatly disagree, and a player with no way to see that
        // reasonably concludes the app lost track of its own story.
        <p className="text-xs">
          <span className="font-medium">
            {others.map((o) => o.characterName).join(", ")} remember
            {others.length === 1 ? "s" : ""} this differently:
          </span>{" "}
          {others[0].gloss}
        </p>
      ) : null}
    </li>
  );
}

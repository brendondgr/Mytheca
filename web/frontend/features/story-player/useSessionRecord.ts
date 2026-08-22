"use client";

import { useCallback, useRef, useState } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import {
  branchPlaySession,
  closePlaySession,
  createPlaySession,
  deletePlaySession,
  getSessionHistory,
  listPlaySessions,
  editBeat,
  renamePlaySession,
  rewindPlaySession,
} from "@/lib/api";
import type { SessionSummary, StandingItem } from "@/lib/events";
import type { ResolvedScenario } from "@/lib/types";
import { buildScene, type SceneChoice, type SceneMessage, type StatChip } from "./scene-data";
import {
  replaceBeatText,
  latestContextTokens,
  latestGuidance,
  latestPov,
  rehydrateFromHistory,
  type PresenceMap,
  type TraceTurn,
} from "./turn-stream";
import { mostRecent } from "./playthroughs";

/**
 * The writers `useSessionRecord` needs to put a loaded play-through on screen.
 *
 * Passed in rather than owned here because the scene's state belongs to `useScenePlay`. The
 * point is that ONE place decides what opening a session does to the screen, and every
 * operation — first load, tray switch, branch, rewind — goes through it, instead of each
 * re-implementing "replace the transcript" slightly differently.
 */
export interface SceneWriters {
  /** Accepts an updater, so an optimistic edit can read the current transcript. */
  setMessages: Dispatch<SetStateAction<SceneMessage[]>>;
  setStats: (s: StatChip[]) => void;
  setStatsByChar: (s: Record<string, StatChip[]>) => void;
  setPresenceByChar: (p: PresenceMap) => void;
  setTraceTurns: (t: TraceTurn[]) => void;
  setChoices: (c: SceneChoice[]) => void;
  setPov: (id: string | null) => void;
  setGuidance: (g: string) => void;
  setComposer: (c: string) => void;
  setLiveContextTokens: (n: number | null) => void;
  setStreamError: (e: string | null) => void;
  /** What an earlier turn could not deliver and the next one will re-owe. */
  setStanding: (items: StandingItem[]) => void;
  notify: (input: { message: string; variant?: "success" | "error" | "info" }) => unknown;
}

/**
 * The play-through **record**: which stories exist for this scenario, which one is open, and
 * every operation that changes one after the fact — switch, start fresh, rename, delete,
 * branch, rewind.
 *
 * Split out of `useScenePlay` when that file passed the repo's 800-line ceiling, so one hook
 * is about *playing* a scene and this one is about *the record of it*. `useScenePlay`
 * re-exports this surface unchanged, so nothing downstream needs to know the split happened
 * — `docs/plans/reach.md` in particular relies on that stability.
 */
export function useSessionRecord({
  scenario,
  sessionRef,
  rememberSession,
  setSessionId,
  baselineRef,
  sendingRef,
  apply,
}: {
  scenario: ResolvedScenario;
  sessionRef: RefObject<string | null>;
  rememberSession: (id: string) => void;
  setSessionId: (id: string | null) => void;
  baselineRef: RefObject<Record<string, StatChip[]>>;
  sendingRef: RefObject<boolean>;
  apply: SceneWriters;
}) {
  // Every play-through of this scenario, most-recently-played first — the tray's rows.
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  /** Set immediately after a rewind, so the transcript can say what just happened. */
  const [rewound, setRewound] = useState<{
    removedEvents: number;
    snapshotSessionId: string | null;
  } | null>(null);
  /**
   * The last beat we know is persisted, for the optimistic-concurrency precondition on the
   * record-mutating endpoints. A ref rather than state: it is read at call time by a
   * callback, and re-rendering the whole player because a seq advanced would be waste.
   */
  const latestSeqRef = useRef<number | null>(null);

  /** Re-read the play-through list (after create / rename / delete / the first turn). */
  const refreshSessions = useCallback(async () => {
    const list = await listPlaySessions(scenario.id).catch(() => ({ sessions: [] }));
    setSessions(list.sessions);
    return list.sessions;
  }, [scenario.id]);

  /**
   * Replace the on-screen scene with one play-through's persisted history.
   *
   * This is the single path by which a session becomes "the open one" — first load, a tray
   * switch, and (in later phases) branch and rewind all route through it, so there is one
   * place that knows how to swap the transcript, stats, presence, POV and traces together.
   * Resetting `choices` matters: a stale branch_choices row from the outgoing play-through
   * would otherwise sit under the incoming one's last beat.
   */
  const loadSession = useCallback(
    async (targetId: string) => {
      const base = baselineRef.current;
      const history = await getSessionHistory(scenario.id, targetId);
      // The precondition the record-mutating endpoints check against.
      latestSeqRef.current = history.events.reduce(
        (top, e) => (typeof e.seq === "number" && e.seq > top ? e.seq : top),
        -1,
      );
      const scene = rehydrateFromHistory(history.events, history.traces, base);
      rememberSession(history.session.id);
      // Restore the "Speaking as" selection from the most recent user_turn's pov, so the
      // next line continues in that character's voice (null → the guide/narrator default).
      apply.setPov(latestPov(history.events));
      // What the player last asked the scene to do, back in the box they asked it from.
      apply.setGuidance(latestGuidance(history.events));
      // The debt the next turn will re-owe, shown up front rather than sprung mid-turn.
      apply.setStanding(history.standingDirection ?? []);
      // Seed the dial with the resumed session's last real context-token count (null when
      // none was recorded → the estimate fallback is used until the next turn streams one).
      apply.setLiveContextTokens(latestContextTokens(history.traces));
      apply.setMessages(scene.messages.length ? scene.messages : buildScene(scenario).messages);
      if (scene.stats.length) apply.setStats(scene.stats);
      apply.setStatsByChar(Object.keys(scene.statsByChar).length ? scene.statsByChar : base);
      apply.setPresenceByChar(scene.presenceByChar);
      apply.setTraceTurns(scene.traceTurns);
      apply.setChoices([]);
      apply.setStreamError(null);
    },
    [scenario, rememberSession, apply, baselineRef],
  );

  /** Switch the scene to another saved play-through. No-op for the one already open. */
  const openSession = useCallback(
    async (targetId: string) => {
      if (targetId === sessionRef.current) return;
      // Stamp the outgoing one closed first, so recency reflects when it was last *played*
      // rather than when it was last listed.
      const outgoing = sessionRef.current;
      if (outgoing) closePlaySession(scenario.id, outgoing);
      await loadSession(targetId);
      await refreshSessions();
    },
    [scenario.id, loadSession, refreshSessions, sessionRef],
  );

  /**
   * Start a brand-new play-through and switch to it.
   *
   * The transcript resets to the scenario's seed opening rather than to nothing: an empty
   * session has no events, so replaying it would leave the reader staring at a blank column
   * where the scene intro belongs.
   */
  const startNewPlaythrough = useCallback(
    async (name?: string) => {
      const outgoing = sessionRef.current;
      if (outgoing) closePlaySession(scenario.id, outgoing);
      const created = await createPlaySession(scenario.id, name);
      const fresh = buildScene(scenario);
      rememberSession(created.id);
      apply.setMessages(fresh.messages);
      apply.setStats(fresh.stats);
      apply.setStatsByChar(baselineRef.current);
      apply.setPresenceByChar({});
      apply.setTraceTurns([]);
      apply.setChoices(fresh.choices);
      apply.setPov(null);
      apply.setGuidance("");
      apply.setStanding([]);
      apply.setLiveContextTokens(null);
      apply.setStreamError(null);
      await refreshSessions();
      return created;
    },
    [scenario, rememberSession, refreshSessions, apply, baselineRef, sessionRef],
  );

  /** Relabel a play-through. A blank name clears it back to the first-player-line fallback. */
  const renamePlaythrough = useCallback(
    async (targetId: string, name: string) => {
      await renamePlaySession(scenario.id, targetId, name.trim() || null);
      await refreshSessions();
    },
    [scenario.id, refreshSessions],
  );

  /**
   * Delete a play-through. Deleting the one currently open moves the scene to whatever is
   * newest afterwards, or to a fresh seed scene when that was the last one — leaving the
   * player looking at the transcript of something that no longer exists would be worse than
   * either.
   */
  const deletePlaythrough = useCallback(
    async (targetId: string) => {
      await deletePlaySession(scenario.id, targetId);
      const remaining = await refreshSessions();
      if (targetId !== sessionRef.current) return;
      const next = mostRecent(remaining);
      if (next) {
        await loadSession(next.id);
        return;
      }
      const fresh = buildScene(scenario);
      sessionRef.current = null;
      setSessionId(null);
      apply.setMessages(fresh.messages);
      apply.setStats(fresh.stats);
      apply.setStatsByChar(baselineRef.current);
      apply.setPresenceByChar({});
      apply.setTraceTurns([]);
      apply.setChoices(fresh.choices);
      apply.setPov(null);
      apply.setLiveContextTokens(null);
    },
    [scenario, refreshSessions, loadSession, apply, baselineRef, setSessionId, sessionRef],
  );

  /**
   * Fork this play-through at a beat and move into the fork. The original is untouched and
   * stays in the tray, which is the whole reason branch is safe to offer on every beat.
   */
  const branchFrom = useCallback(
    async (eventId: string, name?: string) => {
      const sid = sessionRef.current;
      if (!sid || sendingRef.current) return;
      const fork = await branchPlaySession(scenario.id, sid, {
        atEventId: eventId,
        name,
        expectedSeq: latestSeqRef.current ?? undefined,
      });
      closePlaySession(scenario.id, sid);
      await loadSession(fork.id);
      await refreshSessions();
      apply.notify({
        message: "Branched — the original is still in your play-throughs.",
        variant: "success",
      });
      return fork;
    },
    [scenario.id, loadSession, refreshSessions, apply, sessionRef],
  );

  /**
   * Cut this play-through back to a beat and hand the player's own line back.
   *
   * The reload is deliberate rather than a local truncation of `messages`: `loadSession` is
   * the one path already proven to turn persisted rows into a faithful transcript, and a
   * second, subtly different truncation is exactly how the two would drift.
   */
  const rewindTo = useCallback(
    async (eventId: string) => {
      const sid = sessionRef.current;
      if (!sid || sendingRef.current) return;
      const result = await rewindPlaySession(scenario.id, sid, {
        atEventId: eventId,
        keepSnapshot: true,
        expectedSeq: latestSeqRef.current ?? undefined,
      });
      await loadSession(sid);
      await refreshSessions();
      // The player's own words come back, editable, with the direction and attachments they
      // rode in with. This is what makes a rewind a prompt rather than just a deletion.
      const restored = result.restoredTurn;
      if (restored) {
        apply.setComposer(restored.text);
        apply.setGuidance(restored.guidance ?? "");
        apply.setPov(restored.pov ?? null);
      }
      setRewound({
        removedEvents: result.removedEvents,
        snapshotSessionId: result.snapshotSessionId,
      });
      return result;
    },
    [scenario.id, loadSession, refreshSessions, sessionRef],
  );

  /**
   * Rewrite one beat's prose.
   *
   * Optimistic: the new wording lands in the transcript immediately and is rolled back if the
   * write fails. An edit is a small, local, obviously-reversible change — making the player
   * watch a spinner for it would be worse than the rare revert.
   */
  const editBeatText = useCallback(
    async (eventId: string, text: string) => {
      const sid = sessionRef.current;
      if (!sid || sendingRef.current) return;
      let previous: SceneMessage[] = [];
      apply.setMessages((current) => {
        previous = current;
        return replaceBeatText(current, eventId, text);
      });
      try {
        await editBeat(scenario.id, sid, eventId, {
          text,
          expectedSeq: latestSeqRef.current ?? undefined,
        });
      } catch (err) {
        apply.setMessages(() => previous);
        apply.notify({
          message: err instanceof Error ? err.message : "That edit could not be saved.",
          variant: "error",
        });
      }
    },
    [scenario.id, apply, sessionRef],
  );

  return {
    sessions,
    editBeatText,
    refreshSessions,
    loadSession,
    openSession,
    startNewPlaythrough,
    renamePlaythrough,
    deletePlaythrough,
    branchFrom,
    rewindTo,
    rewound,
    clearRewound: () => setRewound(null),
    latestSeqRef,
  };
}

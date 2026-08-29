"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "@/lib/api";
import type { StorylineScope } from "@/lib/types";
import {
  type AgentPanelState,
  type AppliedFields,
  defaultScope,
  emptyPanel,
  foldAgentFrame,
  planToFieldPatch,
  toggleWritable,
} from "./storylineAgent";

interface Options {
  mode: "create" | "edit";
  storylineId?: string;
  /** Read the author's current form values (sent as the agent's context each turn). */
  getFields: () => api.StorylineFieldsSnapshot;
  /**
   * Read the grounding text of the author's Draft-selected context files. Read per
   * turn (like `getFields`) so a file dropped mid-conversation is picked up by the
   * next message. Omit when the host has no context panel.
   */
  getDocsOverview?: () => string | undefined;
  /** Apply approved field values to the form (create: fill; edit: mirror what was saved). */
  onApplied: (patch: AppliedFields) => void;
}

/**
 * The agentic storyline editor/creator panel state + actions.
 *
 * Conversation memory is **client-session**: the whole message history is held here
 * and sent to the server each turn, so the author can discuss first and implement
 * later. `newChat` clears it. Approval applies the plan through the validated apply
 * endpoint (edit) or fills the create form (create).
 */
export function useStorylineAgent(opts: Options) {
  const [scope, setScope] = useState<StorylineScope>(() => defaultScope());
  const [panel, setPanel] = useState<AgentPanelState>(emptyPanel);
  const [busy, setBusy] = useState(false);
  const [applying, setApplying] = useState(false);

  // Refs mirror the latest values so the async actions read them synchronously.
  const panelRef = useRef(panel);
  const scopeRef = useRef(scope);
  const abortRef = useRef<AbortController | null>(null);
  const busyRef = useRef(false);
  const applyingRef = useRef(false);

  const update = useCallback((fn: (p: AgentPanelState) => AgentPanelState) => {
    setPanel((prev) => {
      const next = fn(prev);
      panelRef.current = next;
      return next;
    });
  }, []);

  useEffect(() => {
    scopeRef.current = scope;
  }, [scope]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const setWritable = useCallback((key: string) => {
    setScope((s) => {
      const next = toggleWritable(s, key);
      scopeRef.current = next;
      return next;
    });
  }, []);

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || busyRef.current) return;
      busyRef.current = true;
      setBusy(true);

      const history = [...panelRef.current.messages, { role: "user" as const, content }];
      update((p) => ({ ...p, messages: history, streaming: "", pendingPlan: null, error: null }));

      const controller = new AbortController();
      abortRef.current = controller;
      const body: api.StorylineAgentBody = {
        scope: scopeRef.current,
        messages: history,
        fields: opts.getFields(),
        docsOverview: opts.getDocsOverview?.(),
      };
      try {
        const stream =
          opts.mode === "edit" && opts.storylineId
            ? api.storylineAgentEditStream(opts.storylineId, body, controller.signal)
            : api.storylineAgentCreateStream(body, controller.signal);
        for await (const frame of stream) {
          if (controller.signal.aborted) return;
          update((p) => foldAgentFrame(p, frame));
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        update((p) => ({ ...p, error: (err as Error).message || "The assistant failed." }));
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    [opts, update],
  );

  const approve = useCallback(async () => {
    const plan = panelRef.current.pendingPlan;
    if (!plan || applyingRef.current) return;
    applyingRef.current = true;
    setApplying(true);
    const snapshot = opts.getFields();
    const currentStats = snapshot.stats ?? [];
    const currentStyle = snapshot.styleBlocks ?? {};
    try {
      if (opts.mode === "edit" && opts.storylineId) {
        const res = await api.applyStorylineAgentPlan(opts.storylineId, {
          scope: scopeRef.current,
          plan,
          baseVersion: panelRef.current.baseVersion,
        });
        opts.onApplied(planToFieldPatch(plan, currentStats, currentStyle));
        const note = res.applied.length ? res.applied.join(", ") : "no changes";
        update((p) => ({
          ...p,
          pendingPlan: null,
          messages: [...p.messages, { role: "assistant", content: `Applied — ${note}.` }],
        }));
      } else {
        opts.onApplied(planToFieldPatch(plan, currentStats, currentStyle));
        update((p) => ({
          ...p,
          pendingPlan: null,
          messages: [...p.messages, { role: "assistant", content: "Applied to the form." }],
        }));
      }
    } catch (err) {
      update((p) => ({ ...p, error: (err as Error).message || "Could not apply the plan." }));
    } finally {
      applyingRef.current = false;
      setApplying(false);
    }
  }, [opts, update]);

  const dismissPlan = useCallback(() => update((p) => ({ ...p, pendingPlan: null })), [update]);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    busyRef.current = false;
    setBusy(false);
    const fresh = emptyPanel();
    panelRef.current = fresh;
    setPanel(fresh);
  }, []);

  return {
    scope,
    setWritable,
    panel,
    busy,
    applying,
    send,
    refine: send,
    approve,
    dismissPlan,
    newChat,
  };
}

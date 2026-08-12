"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Toast,
  type ToastAction,
  type ToastItem,
  type ToastVariant,
} from "@/components/ui/Toast";

export interface NotifyInput {
  message: string;
  variant?: ToastVariant;
  title?: string;
  /** Auto-dismiss delay; `0` keeps the toast until dismissed. */
  durationMs?: number;
  /** Optional single action button (e.g. Undo). */
  action?: ToastAction;
}

interface ToastContextValue {
  notify: (input: NotifyInput) => string;
  dismiss: (id: string) => void;
}

/**
 * Default no-op so any component may call `useToast()` without a provider (e.g.
 * a modal rendered in isolation under test) — the notification is simply a
 * cross-cutting nicety, never a hard dependency.
 */
const NOOP: ToastContextValue = { notify: () => "", dismiss: () => {} };

const ToastContext = createContext<ToastContextValue>(NOOP);

export function useToast(): ToastContextValue {
  return useContext(ToastContext);
}

let counter = 0;
function nextId(): string {
  counter += 1;
  return `toast-${counter}`;
}

const DEFAULT_DURATION = 6000;

/** A live auto-dismiss countdown: the running timer plus enough bookkeeping to
 * stop and restart it where it left off. */
interface Countdown {
  timer: ReturnType<typeof setTimeout> | null;
  /** Time still owed when the timer was last (re)started. */
  remainingMs: number;
  /** When that timer was started, so a pause can subtract the elapsed part. */
  startedAt: number;
}

/**
 * App-global notifications. Mount once near the root; children call `useToast()`
 * to raise a top-right toast (errors from the agentic flows land here).
 *
 * Auto-dismiss is pausable. Hovering or focusing a toast holds its timer, and
 * leaving resumes it with only the remaining time — without this, an error long
 * enough to be worth reading disappears while you are reading it, which is the
 * exact moment a toast is least welcome.
 */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const countdowns = useRef<Map<string, Countdown>>(new Map());

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
    const countdown = countdowns.current.get(id);
    if (countdown?.timer) clearTimeout(countdown.timer);
    countdowns.current.delete(id);
  }, []);

  /** (Re)start a toast's timer for whatever time it still has owed. */
  const run = useCallback(
    (id: string, remainingMs: number) => {
      countdowns.current.set(id, {
        timer: setTimeout(() => dismiss(id), remainingMs),
        remainingMs,
        startedAt: Date.now(),
      });
    },
    [dismiss],
  );

  const pause = useCallback((id: string) => {
    const countdown = countdowns.current.get(id);
    if (!countdown?.timer) return;
    clearTimeout(countdown.timer);
    const elapsed = Date.now() - countdown.startedAt;
    countdowns.current.set(id, {
      timer: null,
      // Never below zero: a pause after the timer would have fired should
      // resume to an immediate dismiss, not to a negative delay.
      remainingMs: Math.max(0, countdown.remainingMs - elapsed),
      startedAt: countdown.startedAt,
    });
  }, []);

  const resume = useCallback(
    (id: string) => {
      const countdown = countdowns.current.get(id);
      // Already running, or never had a timer (durationMs was 0) — nothing to do.
      if (!countdown || countdown.timer) return;
      run(id, countdown.remainingMs);
    },
    [run],
  );

  const notify = useCallback(
    ({
      message,
      variant = "info",
      title,
      durationMs = DEFAULT_DURATION,
      action,
    }: NotifyInput) => {
      const id = nextId();
      setItems((prev) => [
        ...prev,
        { id, message, variant, title, action, durationMs },
      ]);
      if (durationMs > 0) run(id, durationMs);
      return id;
    },
    [run],
  );

  const value = useMemo(() => ({ notify, dismiss }), [notify, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <Toast
        items={items}
        onDismiss={dismiss}
        onPause={pause}
        onResume={resume}
      />
    </ToastContext.Provider>
  );
}

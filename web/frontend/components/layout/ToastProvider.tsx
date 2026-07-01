"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import { Toast, type ToastItem, type ToastVariant } from "@/components/ui/Toast";

export interface NotifyInput {
  message: string;
  variant?: ToastVariant;
  title?: string;
  /** Auto-dismiss delay; `0` keeps the toast until dismissed. */
  durationMs?: number;
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

/**
 * App-global notifications. Mount once near the root; children call `useToast()`
 * to raise a top-right toast (errors from the agentic flows land here). Timers
 * are tracked so an early manual dismiss cancels the auto-dismiss.
 */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const notify = useCallback(
    ({
      message,
      variant = "info",
      title,
      durationMs = DEFAULT_DURATION,
    }: NotifyInput) => {
      const id = nextId();
      setItems((prev) => [...prev, { id, message, variant, title }]);
      if (durationMs > 0) {
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), durationMs),
        );
      }
      return id;
    },
    [dismiss],
  );

  const value = useMemo(() => ({ notify, dismiss }), [notify, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <Toast items={items} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

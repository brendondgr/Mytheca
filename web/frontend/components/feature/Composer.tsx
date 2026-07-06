import { useLayoutEffect, useRef, type RefObject } from "react";

/** Maximum visible height of the textarea before it becomes scrollable (~10 lines). */
const MAX_HEIGHT = 240;

/** Bottom composer: auto-growing textarea + circular Send button. */
export function Composer({
  value,
  onChange,
  onSend,
  sendDisabled = false,
  inputRef,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  /**
   * When true, only sending is blocked (button disabled + Enter guarded).
   * The textarea stays editable so the player can keep typing while a turn streams.
   */
  sendDisabled?: boolean;
  /** Lets the parent move focus here after a suggestion is written into the box. */
  inputRef?: RefObject<HTMLTextAreaElement | null>;
}) {
  const internalRef = useRef<HTMLTextAreaElement>(null);
  const ref = (inputRef as RefObject<HTMLTextAreaElement>) ?? internalRef;

  /** Resize the textarea to fit its content, capped at MAX_HEIGHT. */
  function resize(el: HTMLTextAreaElement) {
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
    el.style.overflowY = el.scrollHeight > MAX_HEIGHT ? "auto" : "hidden";
  }

  // Re-run resize whenever `value` changes externally (e.g. suggestion select).
  useLayoutEffect(() => {
    const el = ref.current;
    if (el) resize(el);
  }, [value, ref]);

  return (
    /* Outer band: transparent, no background — just positions the centered panel. */
    <div className="flex-none px-[16px] pb-[16px] sm:px-[30px] sm:pb-[20px]">
      {/* The single visual unit: the chat box panel. */}
      <div className="relative mx-auto max-w-[720px] rounded-t-[14px] rounded-b-[4px] border border-field-bd bg-field focus-within:border-accent transition-colors duration-150">
        <textarea
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            resize(e.currentTarget);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!sendDisabled && value.trim()) onSend();
            }
          }}
          // textarea is always enabled — only send is blocked while streaming
          aria-label="Your message"
          placeholder={sendDisabled ? "The scene responds…" : "Speak, or describe what you do…"}
          className="block w-full resize-none bg-transparent p-[12px_56px_12px_14px] font-body text-[15px] text-ink placeholder:text-mute2 focus:outline-none"
          style={{ overflowY: "hidden" }}
        />
        {/* Circular Send button — absolutely positioned bottom-right inside the panel. */}
        <button
          type="button"
          onClick={onSend}
          disabled={sendDisabled}
          aria-label="Send"
          className="absolute right-[8px] bottom-[8px] grid h-[38px] w-[38px] place-items-center rounded-full bg-accent text-[#F6ECDA] transition-[filter] hover:brightness-110 disabled:opacity-50 disabled:hover:brightness-100"
        >
          {/* Paper-plane / send arrow — 18 px, centered by the grid parent. */}
          <svg
            aria-hidden="true"
            width="18"
            height="18"
            viewBox="0 0 18 18"
            fill="currentColor"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path d="M1.5 1.5L16.5 9L1.5 16.5V10.5L12 9L1.5 7.5V1.5Z" />
          </svg>
        </button>
      </div>
    </div>
  );
}

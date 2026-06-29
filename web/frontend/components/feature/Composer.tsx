/** Bottom composer: the message input and send. */
export function Composer({
  value,
  onChange,
  onSend,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
}) {
  return (
    <div className="velora-header flex-none border-t border-hair-strong p-[13px_16px] sm:p-[13px_30px]">
      <div className="mx-auto flex max-w-[720px] items-center gap-[10px]">
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSend();
          }}
          aria-label="Your message"
          placeholder="Speak, or describe what you do…"
          className="flex-1 rounded-[3px] border border-field-bd bg-field p-[10px_14px] font-body text-[15px] text-ink focus:border-accent focus:outline-none"
        />
        <button
          type="button"
          onClick={onSend}
          className="flex-none rounded-[3px] bg-accent p-[11px_20px] font-mono text-[11px] tracking-[0.1em] text-[#F6ECDA] uppercase hover:brightness-110"
        >
          Send ▸
        </button>
      </div>
    </div>
  );
}

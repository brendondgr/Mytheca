/** The × dismiss control used in modal headers. */
export function CloseButton({ onClose }: { onClose: () => void }) {
  return (
    <button
      type="button"
      onClick={onClose}
      aria-label="Close"
      className="cursor-pointer text-[20px] leading-none text-mute2 hover:text-accent"
    >
      ×
    </button>
  );
}

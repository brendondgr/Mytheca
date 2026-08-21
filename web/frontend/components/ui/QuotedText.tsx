import { Fragment } from "react";

// A run wrapped in double quotes — straight ("…") or curly ("…"). The capturing group makes
// String.split keep the delimiters so they can be rendered (and kept visible) as bold.
const QUOTED_SPLIT = /("[^"]*"|“[^”]*”)/g;
const IS_QUOTED = /^(?:"[^"]*"|“[^”]*”)$/;

/**
 * Renders `text`, bolding any run wrapped in double quotes — straight or curly — while
 * keeping the quotation marks themselves visible (request #4). Used across the transcript
 * bubbles so spoken/quoted dialogue reads with emphasis inside otherwise-plain prose.
 *
 * `color` tints the quoted runs. In a character beat this is the speaker's own colour,
 * mixed toward `--quote-tint` so the same rule reads well on a dark bubble (lifted) and on
 * the parchment theme's cream one (deepened) — a straight lighten would wash out there.
 * Unquoted prose is never tinted: it stays plain body text.
 */
export function QuotedText({ text, color }: { text: string; color?: string }) {
  const parts = text.split(QUOTED_SPLIT);
  return (
    <>
      {parts.map((part, i) =>
        IS_QUOTED.test(part) ? (
          <strong key={i} className="font-semibold" style={color ? { color } : undefined}>
            {part}
          </strong>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

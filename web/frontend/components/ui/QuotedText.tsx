import { Fragment } from "react";

// A run wrapped in double quotes — straight ("…") or curly ("…"). The capturing group makes
// String.split keep the delimiters so they can be rendered (and kept visible) as bold.
const QUOTED_SPLIT = /("[^"]*"|“[^”]*”)/g;
const IS_QUOTED = /^(?:"[^"]*"|“[^”]*”)$/;

/**
 * Renders `text`, bolding any run wrapped in double quotes — straight or curly — while
 * keeping the quotation marks themselves visible (request #4). Used across the transcript
 * bubbles so spoken/quoted dialogue reads with emphasis inside otherwise-plain prose.
 */
export function QuotedText({ text }: { text: string }) {
  const parts = text.split(QUOTED_SPLIT);
  return (
    <>
      {parts.map((part, i) =>
        IS_QUOTED.test(part) ? (
          <strong key={i} className="font-semibold">
            {part}
          </strong>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

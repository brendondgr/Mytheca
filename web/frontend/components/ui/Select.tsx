import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

/**
 * The one native `<select>` chrome.
 *
 * **Why the size is two sizes.** `--fs-field` is pinned at 16px in every text-size preset
 * (`styles/themes.css`), Compact included, and the comment there says why: below 16px, iOS
 * Safari zooms the viewport when a form control takes focus. That is a real constraint where
 * there is a touch keyboard and no constraint at all where there is a mouse — but every
 * select in the app paid it everywhere, which is how a 264px popover ended up holding six
 * 16px monospaced fields, each the loudest thing on the screen.
 *
 * `text-field pointer-fine:text-ui` splits it on the condition that actually decides it.
 * **Not on a breakpoint**, which was the first attempt and is wrong: an iPhone 14 Pro Max in
 * landscape is 932 CSS px wide, so a `sm:` split hands the phone that most needs the floor a
 * 13px field. `pointer: fine` is the same predicate `styles/motion.css` uses for the 44px
 * touch floor, so the two rules agree about what a phone is. Do not "simplify" this to one
 * size: the 16px is load-bearing on a coarse pointer and wrong on a fine one.
 *
 * `focus:outline-none` is the field's opt-out from the boxy indicator in favour of
 * `focus:border-accent`, and it applies to POINTER focus only: `globals.css`'s bare
 * `:focus-visible` rule is UNLAYERED, so a Tailwind utility in `@layer utilities` cannot
 * turn it off. A keyboard user keeps the 2px accent outline. That is the intended
 * behaviour, not an oversight in the class list.
 *
 * Height is not set here either. On a coarse pointer the global floor in `styles/motion.css`
 * grows every `select` to 44px, so a fixed height would either fight that rule or duplicate
 * it. Padding sets the resting size and the floor raises it where a finger is involved.
 */
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, ...props }, ref) {
    return (
      <select
        ref={ref}
        {...props}
        className={cn(
          "rounded-xs border border-field-bd bg-field px-xs py-2xs font-mono text-field text-ink",
          "focus:border-accent focus:outline-none disabled:opacity-60 pointer-fine:text-ui",
          className,
        )}
      />
    );
  },
);

import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

/**
 * The one native `<select>` chrome.
 *
 * **Why the size is two sizes.** `--fs-field` is pinned at 16px in every text-size preset
 * (`styles/themes.css`), Compact included, and the comment there says why: below 16px, iOS
 * Safari zooms the viewport when a form control takes focus. That is a real constraint on a
 * phone and no constraint at all on a mouse — but every select in the app paid it at every
 * width, which is how a 264px popover ended up with six 16px monospaced fields in it, each
 * the loudest thing on the screen.
 *
 * `text-field sm:text-ui` makes the same split `--control` already makes (44px below `sm`,
 * 34px above): the mobile contract is kept exactly, and the dense desktop chrome the design
 * system asks for — "small and quiet" — is finally what desktop gets. Do not "simplify" this
 * to one size; the 16px is load-bearing below `sm` and wrong above it.
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
          "focus:border-accent focus:outline-none disabled:opacity-60 sm:text-ui",
          className,
        )}
      />
    );
  },
);

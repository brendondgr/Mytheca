import { cn } from "@/lib/cn";

/**
 * Entrance choreography, as a component rather than a remembered convention.
 *
 * Two effects, both already defined in `styles/motion.css` and both fail-open:
 *
 *  - `<Reveal>` — a single element rising as it scrolls into view.
 *  - `<Reveal.Group>` — a set arriving in sequence. The stagger is driven by a
 *    `--i` custom property per child, capped at 8 steps so a forty-item list
 *    does not take two seconds to finish arriving.
 *
 * Neither carries a hidden base state. If the CSS never loads, the JS never
 * runs, the browser lacks `view()` and lacks IntersectionObserver, or the user
 * asked for reduced motion, the content is simply THERE. That is the single
 * most important property of this file and the reason the group writes its
 * index to a custom property instead of, say, an opacity.
 */
export function Reveal({
  as: As = "div",
  className,
  children,
  ...rest
}: {
  as?: "div" | "section" | "li" | "article";
  className?: string;
  children: React.ReactNode;
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <As className={cn("reveal", className)} {...rest}>
      {children}
    </As>
  );
}

/**
 * A choreographed group entrance.
 *
 * `--i` is set per child from its index. This is a presentational custom
 * property, not a hidden state: with no stylesheet it means nothing and the
 * children render normally.
 */
function Group({
  as: As = "div",
  className,
  children,
  ...rest
}: {
  as?: "div" | "ul" | "ol" | "section";
  className?: string;
  children: React.ReactNode;
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <As className={cn("stagger", className)} {...rest}>
      {children}
    </As>
  );
}

/**
 * The index carrier for a `Reveal.Group` child.
 *
 * Kept separate from `Reveal` because a staggered child is animated by its
 * PARENT's `.stagger > *` rule — giving it `.reveal` as well would run two
 * entrances on one element.
 */
function Item({
  index,
  as: As = "div",
  className,
  style,
  children,
  ...rest
}: {
  index: number;
  as?: "div" | "li" | "article";
  className?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <As
      className={className}
      style={{ ...style, ["--i" as string]: index }}
      {...rest}
    >
      {children}
    </As>
  );
}

Reveal.Group = Group;
Reveal.Item = Item;

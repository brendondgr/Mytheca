import Link from "next/link";
import { Page, Stack } from "@/components/ui/Page";

export const metadata = { title: "Not found" };

/**
 * The 404. Previously this fell through to Next's stock page, which carries
 * none of the theme — a jarring white slab in the middle of a dark manuscript.
 */
export default function NotFound() {
  return (
    <Page measure="prose" className="flex items-center justify-center">
      <Stack gap="lg" className="text-center">
        <p className="font-mono text-eyebrow tracking-[0.2em] text-mute uppercase">
          404
        </p>
        <h1 className="font-display text-step-2 font-bold text-ink">
          This page is not in the library
        </h1>
        <p className="font-body text-body text-ink-soft">
          The storyline, scene or document you asked for does not exist — or it
          was deleted after the link was made.
        </p>
        <div>
          <Link
            href="/"
            className="inline-flex items-center rounded-xs border border-field-bd px-md py-sm font-mono text-ui tracking-[0.1em] text-accent uppercase hover:bg-accent hover:text-on-accent"
          >
            Back to the Library
          </Link>
        </div>
      </Stack>
    </Page>
  );
}

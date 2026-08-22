/**
 * The line where verbatim memory stops.
 *
 * The owner's complaint that the cast *"forgets what happens so often"* is two things. Part of
 * it is a real defect in how a direction is tracked (fixed elsewhere). The rest is that
 * forgetting happens **invisibly**: a scene silently stops carrying its oldest beats and
 * nothing anywhere says so, so every consequence of it reads as the model being stupid.
 *
 * This is the marker that makes it visible — a quiet hairline above the oldest beat the cast
 * still reads word for word.
 *
 * **Known imprecision, deliberately shipped.** Transcript messages and buffer beats are not
 * exactly 1:1 — an internal thought folds into its speaker's beat — so the line is accurate to
 * within a beat or two. That is enough for its job, which is to tell the player *that* there is
 * an edge and roughly where. The exact figures live in the scene-memory panel, which reads them
 * from the engine rather than counting rendered messages. Recorded in `docs/checklist.md`.
 */
export function MemoryEdge({
  droppedBeats,
  summarised = false,
}: {
  /** How many older beats fell out of the window. Renders nothing at zero. */
  droppedBeats: number;
  /** Whether those beats were kept as a summary (compaction on) or simply dropped. */
  summarised?: boolean;
}) {
  if (droppedBeats <= 0) return null;

  return (
    <div className="flex items-center gap-[8px] py-[6px]" role="separator">
      <span aria-hidden className="h-px flex-1 bg-hair-strong" />
      <span className="flex-none text-center font-mono text-[9px] leading-[1.5] tracking-[0.14em] text-mute2 uppercase">
        {summarised
          ? `— everything above here is remembered as a summary (${droppedBeats}) —`
          : `— the cast no longer reads the ${droppedBeats} beat${droppedBeats === 1 ? "" : "s"} above —`}
      </span>
      <span aria-hidden className="h-px flex-1 bg-hair-strong" />
    </div>
  );
}

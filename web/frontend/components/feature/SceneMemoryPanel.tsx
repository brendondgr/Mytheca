"use client";

import { useEffect, useState } from "react";
import { AsyncPanel, type AsyncStatus } from "@/components/ui/AsyncPanel";
import { CloseButton } from "@/components/ui/CloseButton";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { getSceneKnowledge, postSessionRecap } from "@/lib/api";
import type { SceneKnowledge } from "@/lib/events";

/**
 * What the scene knows — the same facts as the Inspector, written for a player.
 *
 * The Inspector answers *"what did the loop do"*: intent, planner choice, per-beat thinking,
 * token counts. This answers *"what does the scene know"*, which is the question a player
 * actually has — how far back can it remember, what did I attach, what did it look up, what
 * did I ask for and did it happen.
 *
 * The app computed every one of these facts already and showed none of them, which is most of
 * the review's finding that nothing explains itself. It is fetched from persisted traces
 * rather than folded off the stream, so it is just as useful on a scene the player came back
 * to as on one mid-turn.
 */
export function SceneMemoryPanel({
  open,
  onClose,
  scenarioId,
  sessionId,
}: {
  open: boolean;
  onClose: () => void;
  scenarioId: string;
  /** `null` before the first turn has created a session — the panel says so. */
  sessionId: string | null;
}) {
  const [status, setStatus] = useState<AsyncStatus>("idle");
  const [data, setData] = useState<SceneKnowledge | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!open || !sessionId) return;
    let alive = true;
    // Resetting to "loading" on each (re)fetch is the intended behaviour, and there is no way
    // to express "a new read just started" without writing state — the same case
    // `features/story-player/useSceneData.ts` documents. `AsyncPanel` gates the indicator
    // behind `useDelayedFlag`, so a fast read shows nothing at all.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setStatus("loading");
    getSceneKnowledge(scenarioId, sessionId)
      .then((res) => {
        if (!alive) return;
        setData(res);
        // A scene that has not run a turn has nothing to report, and an empty state that
        // invites the player to play is a better answer than a panel of zeroes.
        setStatus(res.windowBeats === 0 && !res.direction.items.length ? "empty" : "success");
      })
      .catch(() => alive && setStatus("error"));
    return () => {
      alive = false;
    };
  }, [open, scenarioId, sessionId, nonce]);

  if (!open) return null;

  return (
    <aside
      aria-label="What the scene knows"
      // Below `sm` it takes the full width — while it is open, it IS the view; from `sm` up it
      // docks as a 340px column beside the transcript, matching the Inspector.
      className="flex w-full flex-none flex-col border-l border-hair-strong bg-page sm:w-[340px]"
    >
      <header className="flex flex-none items-start justify-between gap-3 border-b border-hair-strong p-[14px_16px]">
        <div>
          <h2 className="font-display text-body-sm leading-none font-bold text-ink">
            What the scene knows
          </h2>
          <p className="mt-xs font-mono text-eyebrow leading-[1.5] tracking-[0.08em] text-mute uppercase">
            What the cast is reading right now
          </p>
        </div>
        <CloseButton onClose={onClose} className="relative" />
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-[12px_14px]">
        {!sessionId ? (
          <p className="font-body text-body-sm leading-[1.5] text-ink-soft">
            Play a turn and this will show what the cast can see — how far back it remembers,
            the files you attached, what it looked up, and whether what you asked for happened.
          </p>
        ) : (
          <AsyncPanel
            status={status}
            label="What the scene knows"
            errorTitle="That could not be read"
            errorMessage="The scene's context could not be loaded just now."
            onRetry={() => setNonce((n) => n + 1)}
            emptyTitle="Nothing yet"
            emptyMessage="Send a message and this fills in with what the cast can actually see."
          >
            {data ? (
              <Sections data={data} scenarioId={scenarioId} sessionId={sessionId} />
            ) : null}
          </AsyncPanel>
        )}
      </div>
    </aside>
  );
}

/**
 * "Tell me what happened", on demand.
 *
 * Its own async state rather than the panel's, so asking for a recap never blanks out the
 * facts already on screen — the player asked for one more thing, not for the panel to reset.
 */
function RecapSection({
  scenarioId,
  sessionId,
}: {
  scenarioId: string;
  sessionId: string;
}) {
  const [status, setStatus] = useState<AsyncStatus>("idle");
  const [text, setText] = useState("");

  const run = () => {
    setStatus("loading");
    postSessionRecap(scenarioId, sessionId)
      .then((res) => {
        setText(res.text);
        // An empty recap is a real outcome (nothing to say, or no model), and saying so is
        // better than an empty panel that looks broken.
        setStatus(res.text ? "success" : "empty");
      })
      .catch(() => setStatus("error"));
  };

  return (
    <Section title="What happened so far">
      {status === "success" ? (
        <p className="whitespace-pre-wrap">{text}</p>
      ) : status === "loading" ? (
        <p className="text-mute2">Reading the scene back…</p>
      ) : status === "error" ? (
        <p className="text-danger-ink">That could not be written just now.</p>
      ) : status === "empty" ? (
        <p className="text-mute2">There is nothing to recap yet.</p>
      ) : null}
      <button
        type="button"
        onClick={run}
        disabled={status === "loading"}
        className="mt-xs min-h-[28px] rounded-sm border border-field-bd px-sm font-mono text-eyebrow tracking-[0.08em] text-mute uppercase hover:bg-hover hover:text-ink disabled:opacity-50"
      >
        {status === "idle" ? "Recap the scene" : "Write it again"}
      </button>
    </Section>
  );
}

function Sections({
  data,
  scenarioId,
  sessionId,
}: {
  data: SceneKnowledge;
  scenarioId: string;
  sessionId: string;
}) {
  const { direction, retrieval, summary } = data;
  return (
    <div className="flex flex-col gap-lg">
      <Section title="How far back the cast remembers">
        <p>
          The last <strong className="font-semibold">{data.windowBeats}</strong> beat
          {data.windowBeats === 1 ? "" : "s"}, word for word
          {data.budgetTokens ? ` (about ${data.budgetTokens.toLocaleString()} tokens)` : ""}.
          {data.droppedBeats > 0
            ? ` ${data.droppedBeats} older beat${data.droppedBeats === 1 ? "" : "s"} ${
                summary.text ? "have been folded into a summary" : "are no longer read"
              }.`
            : " Nothing has dropped out yet."}
        </p>
        {/* Where the number came from matters: "we asked the model" and "we guessed" are
            different claims, and only one deserves to be trusted with a full window. */}
        {data.windowSource === "fallback" ? (
          <p className="mt-2xs text-mute2">
            The model did not report a context size and none is configured, so a conservative
            default is in force.
          </p>
        ) : null}
      </Section>

      {summary.text ? (
        <Section title="What it has folded into memory">
          <p className="whitespace-pre-wrap">{summary.text}</p>
        </Section>
      ) : null}

      <RecapSection scenarioId={scenarioId} sessionId={sessionId} />

      <Section title="Files you attached">
        {data.taggedNames.length ? (
          <ul className="flex flex-col gap-3xs">
            {data.taggedNames.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        ) : (
          <p className="text-mute2">None on the last message.</p>
        )}
      </Section>

      <Section title="What it looked up">
        <p className={retrieval.fired ? "" : "text-mute2"}>
          {retrieval.fired
            ? retrieval.matched
              ? "Searched the world's lore and folded in what it found."
              : "Searched the world's lore and found nothing to add."
            : "Nothing in your message needed a look-up."}
        </p>
      </Section>

      <Section title="Who it knows about whom">
        {data.relationships.length ? (
          <ul className="flex flex-col gap-2xs">
            {data.relationships.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : (
          <p className="text-mute2">No ties reached the last beat.</p>
        )}
      </Section>

      <Section title="What you asked for, and what landed">
        {direction.items.length ? (
          <ul className="flex flex-col gap-2xs">
            {direction.items.map((item) => {
              const done = direction.delivered.includes(item);
              return (
                <li key={item} className="flex items-start gap-xs">
                  {/* Glyph AND wording, never colour alone. */}
                  <span aria-hidden className={done ? "text-success-ink" : "text-mute2"}>
                    {done ? "✓" : "○"}
                  </span>
                  <span>
                    {item}
                    {done ? "" : " — not confirmed"}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-mute2">You did not direct the last turn.</p>
        )}
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <Eyebrow tracking="0.14em" className="mb-xs block">
        {title}
      </Eyebrow>
      <div className="font-body text-eyebrow leading-[1.5] text-ink-soft">{children}</div>
    </section>
  );
}

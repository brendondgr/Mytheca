"use client";

import { CreateImageBar } from "@/components/feature/CreateImageBar";
import type { ArtStyleId } from "@/lib/api";

/**
 * The two between-turn actions, in one cluster at the foot of the transcript.
 *
 * **Continue** runs a turn with no line from the player at all — the scene simply carries
 * on. Before it, speaking was the only way to move a scene: you could not sit back and
 * watch, and you could not direct without also putting words in your own mouth.
 *
 * It sits first in the tab order because it is the one that advances the story; **Create
 * image** pictures the moment the story is already in. `CreateImageBar` is composed
 * untouched rather than absorbed, so its own behaviour and tests stay exactly as they were.
 */
export function TranscriptFootBar({
  onContinue,
  continuing = false,
  onCreateImage,
  creatingImage = false,
  imageStage = null,
  imageError = null,
  disabled = false,
}: {
  onContinue: () => void;
  continuing?: boolean;
  onCreateImage: (artStyle?: ArtStyleId) => void;
  creatingImage?: boolean;
  imageStage?: "prompt" | "render" | null;
  imageError?: string | null;
  /** True while a turn streams — neither action makes sense mid-sentence. */
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-col gap-[6px]">
      <div className="flex items-center justify-center">
        <button
          type="button"
          onClick={onContinue}
          disabled={disabled || continuing}
          title="Continue — let the scene play on without you saying anything"
          className="flex items-center gap-[7px] rounded-[8px] border border-field-bd px-[13px] py-[6px] font-mono text-[10px] tracking-[0.1em] text-mute uppercase hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:border-field-bd disabled:hover:text-mute"
        >
          <span aria-hidden>▸</span>
          {continuing ? "Continuing…" : "Continue"}
        </button>
      </div>
      <p className="text-center font-mono text-[9px] tracking-[0.06em] text-mute2">
        Let the scene carry on without you
      </p>
      <CreateImageBar
        onCreate={onCreateImage}
        running={creatingImage}
        stage={imageStage}
        error={imageError}
        className="mt-[2px]"
      />
    </div>
  );
}

import type { SessionSummary } from "@/lib/events";

/**
 * The play-through to open when none was asked for: the most recently played.
 *
 * The server already returns the list in recency order, but this reads the newest
 * explicitly rather than taking `sessions[0]`. That index used to BE the whole session
 * model — the story player resumed it unconditionally and threw the rest away, so a scenario
 * could only ever hold one story. Naming the intent keeps the ordering assumption from
 * silently becoming a feature again.
 */
export function mostRecent(sessions: SessionSummary[]): SessionSummary | null {
  if (!sessions.length) return null;
  return sessions.reduce((newest, s) =>
    Date.parse(s.updatedAt) > Date.parse(newest.updatedAt) ? s : newest,
  );
}

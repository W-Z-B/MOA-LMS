import { post } from "../../api/client";
import type { Draft } from "../../api/types-connect";
import { useAiStatus } from "./status";

/** A description the AI suggested for a picture, and how to say it was used once the lecturer has checked it. */
export interface AltSuggestion {
  text: string;
  used: () => void;
}

/**
 * Alternative text suggested for a picture on the course (item 6.11), for the page editor's picture form. Only
 * where GSA has a model that reads pictures and the course has AI drafts switched on; otherwise undefined, and
 * the form offers nothing.
 */
export function useAltSuggestions(siteId: number): ((picture: { id: number }) => Promise<AltSuggestion>) | undefined {
  const [status] = useAiStatus(siteId);
  if (!status?.drafts || !status.pictures) return undefined;
  return async (picture) => {
    const draft = await post<Draft<{ alt_text: string }>>(`/sites/${siteId}/ai/drafts/alt-text/`, { item: picture.id });
    return {
      text: draft.output.alt_text,
      used: () => void post(`/ai/drafts/${draft.draft}/saved/`, { record: "content", id: picture.id }).catch(() => undefined),
    };
  };
}

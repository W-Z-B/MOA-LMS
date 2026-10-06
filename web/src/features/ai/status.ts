import { useEffect, useState } from "react";
import { get } from "../../api/client";
import type { AiStatus } from "../../api/types-connect";

/** AI help on a course as the site screen needs it: null while unknown, or when it cannot be read. */
export function useAiStatus(siteId: number): [AiStatus | null, (status: AiStatus) => void] {
  const [status, setStatus] = useState<AiStatus | null>(null);
  useEffect(() => {
    get<AiStatus>(`/sites/${siteId}/ai/`)
      .then(setStatus)
      .catch(() => setStatus(null));
  }, [siteId]);
  return [status, setStatus];
}

/** Whether the AI help tab is shown: never while AI is off; to a student only while the helper may be used. */
export const showsAiTab = (status: AiStatus | null) => Boolean(status?.enabled && (status.teaching || status.helper_available));

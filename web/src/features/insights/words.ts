/** How the insight screens load their data and say their figures. */

import { useCallback, useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import type { StandingWord } from "../../api/types-insights";
import { dmy } from "../../app/format";

/** Load something for a screen; reload() fetches it again. */
export function useLoad<T>(path: string, fallback: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(() => {
    get<T>(path)
      .then((answer) => {
        setData(answer);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, fallback)));
  }, [path, fallback]);
  useEffect(reload, [reload]);
  return { data, error, reload };
}

/** "62.5%", or a dash when there is nothing to work it out from. */
export const percent = (value: string | null | undefined) => (value == null ? "–" : `${Number(value)}%`);

/** The latest recorded activity, in words. */
export const seen = (iso: string | null) => (iso ? dmy(iso) : "None recorded");

export const STANDING_WORDS: Record<StandingWord, string> = {
  met: "Met",
  not_yet: "Not yet met",
  no_evidence: "No evidence yet",
};

/** An outcome standing in a cell: "Met (70%)". */
export const standingText = (standing: StandingWord, value: string | null) =>
  value == null ? STANDING_WORDS[standing] : `${STANDING_WORDS[standing]} (${Number(value)}%)`;

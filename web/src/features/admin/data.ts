/** Loading and changing things for the staff-development and console screens. */

import { useCallback, useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import type { Paginated } from "../../api/types";

/** A list from the API, paginated or not. */
export const rows = <T,>(answer: Paginated<T> | T[]): T[] => (Array.isArray(answer) ? answer : answer.results);

/** Load something; null path loads nothing. reload() fetches it again. */
export function useData<T>(path: string | null, fallback = "Could not load this.") {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(() => {
    if (path === null) return;
    get<T>(path)
      .then((answer) => {
        setData(answer);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, fallback)));
  }, [path, fallback]);
  useEffect(reload, [reload]);
  return { data, error, reload, setData };
}

/** A change refused before it is sent, in words for the person. */
export class Refusal extends Error {}

/** Run a change, then say what happened (a status) or why not (an alert). */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async (work: () => Promise<string | null>): Promise<boolean> => {
    setBusy(true);
    setDone(null);
    setError(null);
    try {
      setDone(await work());
      return true;
    } catch (err) {
      setError(err instanceof Refusal ? err.message : errorMessage(err, "That did not go through. Check the connection and try again."));
      return false;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, done, error, run };
}

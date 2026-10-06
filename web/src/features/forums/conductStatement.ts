/** The conduct statement in force (item 4.09): read, and whether this person has accepted it. */

import { useCallback, useEffect, useState } from "react";
import { ApiError, errorMessage, get, post } from "../../api/client";
import type { ConductCurrent } from "../../api/types-talk";

/** The refusal the server gives to a post or a message before the statement in force is accepted. */
export const isConductRefusal = (err: unknown) => err instanceof ApiError && err.code === "conduct_not_accepted";

/** The statement in force and whether this person has accepted it; `recheck` reads it again. */
export function useConduct(): { current: ConductCurrent | null; error: string | null; recheck: () => void; accept: () => Promise<void> } {
  const [current, setCurrent] = useState<ConductCurrent | null>(null);
  const [error, setError] = useState<string | null>(null);

  const recheck = useCallback(() => {
    get<ConductCurrent>("/conduct-statements/current/")
      .then((c) => {
        setCurrent(c);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not read the conduct statement.")));
  }, []);

  useEffect(recheck, [recheck]);

  const accept = useCallback(async () => {
    try {
      setCurrent(await post<ConductCurrent>("/conduct-statements/current/accept/"));
    } catch (err) {
      setError(errorMessage(err, "Could not accept the conduct statement."));
    }
  }, []);

  return { current, error, recheck, accept };
}

import type { Licence } from "../../api/types";
import { LICENCE_WORDS, OPEN_LICENCE_WORDS } from "../../api/types-packages";

export interface LicenceValue {
  licence: Licence | "";
  open_licence: string;
  source: string;
}

export const NO_LICENCE: LicenceValue = { licence: "", open_licence: "", source: "" };

/** The fields as the server wants them: no open licence unless it is one, no source for GSA's own. */
export function licenceFields(value: LicenceValue) {
  return {
    licence: value.licence,
    open_licence: value.licence === "open_licence" ? value.open_licence : "",
    source: value.licence === "gsa_own" ? "" : value.source,
  };
}

/** Whose material it is, in words: "CC BY · FAO · FAO e-learning Academy". */
export function licenceLine(item: { licence: Licence | null; open_licence: string; source: string; publisher?: string }): string {
  if (!item.licence) return "Licence not recorded";
  const words =
    item.licence === "open_licence" && item.open_licence ? (OPEN_LICENCE_WORDS[item.open_licence] ?? item.open_licence) : LICENCE_WORDS[item.licence];
  return [words, item.publisher, item.source].filter(Boolean).join(" · ");
}

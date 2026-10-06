import type { Licence } from "../../api/types";
import type { LicenceValue } from "./licence";
import { LICENCE_WORDS, OPEN_LICENCE_WORDS } from "../../api/types-packages";

/**
 * Whose material it is (item 2.19), as the file form asks: GSA's own, under an open licence (which), used
 * under fair dealing or with permission, with the source and credit for anything not GSA's own. `openOnly`
 * is for open educational resources, which are under an open licence by definition.
 */
export function LicenceFields({
  id,
  value,
  onChange,
  openOnly = false,
}: {
  id: string;
  value: LicenceValue;
  onChange: (value: LicenceValue) => void;
  openOnly?: boolean;
}) {
  const choices = (Object.keys(LICENCE_WORDS) as Licence[]).filter((l) => l !== "unknown" && (!openOnly || l === "open_licence"));
  const licence = openOnly ? "open_licence" : value.licence;
  return (
    <>
      {!openOnly && (
        <label>
          Whose material is this?
          <select id={`${id}-licence`} value={licence} onChange={(e) => onChange({ ...value, licence: e.target.value as Licence })} required>
            <option value="" disabled>
              Choose…
            </option>
            {choices.map((l) => (
              <option key={l} value={l}>
                {LICENCE_WORDS[l]}
              </option>
            ))}
          </select>
        </label>
      )}
      {licence === "open_licence" && (
        <label>
          Which open licence
          <select id={`${id}-open`} value={value.open_licence} onChange={(e) => onChange({ ...value, licence: "open_licence", open_licence: e.target.value })} required>
            <option value="" disabled>
              Choose…
            </option>
            {Object.entries(OPEN_LICENCE_WORDS).map(([code, words]) => (
              <option key={code} value={code}>
                {words}
              </option>
            ))}
          </select>
        </label>
      )}
      {licence !== "" && licence !== "gsa_own" && (
        <label>
          Source and credit
          <input
            id={`${id}-source`}
            value={value.source}
            placeholder="Author, title, where it comes from"
            onChange={(e) => onChange({ ...value, licence, source: e.target.value })}
            required
          />
        </label>
      )}
    </>
  );
}

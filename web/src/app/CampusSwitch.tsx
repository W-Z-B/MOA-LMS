import type { Campus } from "../api/types";
import { shortCampus } from "./people";

interface Props {
  campuses: Campus[];
  value: string | null;
  onChange: (code: string | null) => void;
}

/** All campuses or one: narrows the course lists on every page until changed (as in the HRMS). */
export function CampusSwitch({ campuses, value, onChange }: Props) {
  const choices: { code: string | null; label: string }[] = [
    { code: null, label: "All campuses" },
    ...campuses.map((c) => ({ code: c.code, label: shortCampus(c.name) })),
  ];
  return (
    <div className="campus-switch" role="group" aria-label="Campus">
      {choices.map((choice) => (
        <button
          key={choice.label}
          type="button"
          aria-pressed={value === choice.code}
          className={value === choice.code ? "active" : undefined}
          onClick={() => onChange(choice.code)}
        >
          {choice.label}
        </button>
      ))}
    </div>
  );
}

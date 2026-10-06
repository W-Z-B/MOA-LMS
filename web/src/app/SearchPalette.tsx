import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { get } from "../api/client";
import type { Me, SearchHit, SearchHits } from "../api/types";
import { pagesFor } from "./router";

interface Props {
  me: Me;
  phone: boolean;
  onGo: (to: string) => void;
  onClose: () => void;
}

interface Result {
  key: string;
  title: string;
  sub: string;
  to: string;
}

/** The server's groups, in the order they are listed, with what each is called. */
const GROUPS: [keyof SearchHits, string][] = [
  ["sites", "Courses"],
  ["content", "Content"],
  ["assignments", "Assignments"],
  ["quizzes", "Quizzes"],
  ["people", "People"],
];

const EMPTY: SearchHits = { sites: [], content: [], assignments: [], quizzes: [], people: [] };

/**
 * Search for everything (item 2.07, as the HRMS's SearchPalette): courses, content, assignments, quizzes and,
 * for staff, people, from the server, which finds only what the person may open; and the pages of the app.
 * A combobox in a dialog: arrow keys move, Enter opens, Esc closes. Ctrl K opens it from anywhere.
 */
export function SearchPalette({ me, phone, onGo, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHits>(EMPTY);
  const [help, setHelp] = useState<Result[]>([]);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const words = query.trim();
  const asks = words.length >= 2;

  useEffect(() => input.current?.focus(), []);

  useEffect(() => {
    if (!asks) return;
    let current = true;
    const handle = setTimeout(() => {
      get<SearchHits>(`/search/?q=${encodeURIComponent(words)}`)
        .then((found) => current && setHits({ ...EMPTY, ...found }))
        .catch(() => current && setHits(EMPTY));
    }, 200);
    return () => {
      current = false;
      clearTimeout(handle);
    };
  }, [words, asks]);

  // Help (item 7.17): the reader's own help pages, fetched with the first search so the frame stays light.
  useEffect(() => {
    if (!asks) return;
    let current = true;
    import("../features/help/topics")
      .then((topics) => current && setHelp(topics.searchHelp(me, words)))
      .catch(() => current && setHelp([]));
    return () => {
      current = false;
    };
  }, [words, asks, me]);

  const q = words.toLowerCase();
  const matches = (text: string) => !q || text.toLowerCase().includes(q);
  const found = (hit: SearchHit, group: string): Result => ({ key: `${group}-${hit.id}`, title: hit.title, sub: hit.sub, to: hit.link });
  const groups: { label: string; items: Result[] }[] = [
    ...GROUPS.map(([group, label]) => ({
      label,
      items: (asks ? hits[group] : []).filter((hit) => hit.link).map((hit) => found(hit, group)),
    })),
    {
      label: "Pages",
      items: pagesFor(me)
        .filter((page) => page.path !== "/" && !page.later && matches(`${page.label} ${page.desc}`))
        .map((page) => ({ key: `page-${page.path}`, title: page.label, sub: page.desc, to: page.path })),
    },
    { label: "Help", items: asks ? help : [] },
  ].filter((group) => group.items.length > 0);
  const flat = groups.flatMap((group) => group.items);
  const current = Math.min(active, Math.max(flat.length - 1, 0));
  const optionId = (index: number) => `search-option-${index}`;
  const what = me.persona === "student" || me.person_kind === "student" ? "courses, work and pages" : "courses, work, people and pages";

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive(Math.min(current + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive(Math.max(current - 1, 0));
    } else if (e.key === "Enter" && flat[current]) {
      e.preventDefault();
      onGo(flat[current].to);
    }
  }

  // Esc closes from anywhere in the dialog; Tab stays inside it, as a modal dialog's focus must.
  function onDialogKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key !== "Tab" || !dialog.current) return;
    const stops = [...dialog.current.querySelectorAll<HTMLElement>("input, button")];
    const at = stops.indexOf(document.activeElement as HTMLElement);
    const next = (at + (e.shiftKey ? -1 : 1) + stops.length) % stops.length;
    e.preventDefault();
    stops[next]?.focus();
  }

  let index = 0;
  return (
    <div
      className={phone ? "search-backdrop phone" : "search-backdrop"}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="search-dialog" role="dialog" aria-modal="true" aria-label="Search" ref={dialog} onKeyDown={onDialogKeyDown}>
        <div className="search-input">
          <input
            ref={input}
            role="combobox"
            aria-label={`Search ${what}`}
            aria-expanded="true"
            aria-controls="search-results"
            aria-autocomplete="list"
            aria-activedescendant={flat.length > 0 ? optionId(current) : undefined}
            placeholder={`Search ${what}`}
            autoComplete="off"
            spellCheck={false}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
          />
          {phone ? (
            <button type="button" className="link accent" onClick={onClose}>
              Cancel
            </button>
          ) : (
            <kbd aria-hidden="true">Esc</kbd>
          )}
        </div>
        <div className="search-results" id="search-results" role="listbox" aria-label="Results">
          {groups.map((group) => (
            <ul key={group.label} role="group" aria-labelledby={`search-group-${group.label}`}>
              <li role="presentation" className="search-group" id={`search-group-${group.label}`}>
                {group.label}
              </li>
              {group.items.map((item) => {
                const at = index++;
                return (
                  <li
                    key={item.key}
                    id={optionId(at)}
                    role="option"
                    aria-label={item.sub ? `${item.title}, ${item.sub}` : item.title}
                    aria-selected={at === current}
                    className={at === current ? "search-option active" : "search-option"}
                    onMouseMove={() => at !== current && setActive(at)}
                    onClick={() => onGo(item.to)}
                  >
                    <span className="search-title">{item.title}</span>
                    {item.sub && <span className="search-sub">{item.sub}</span>}
                  </li>
                );
              })}
            </ul>
          ))}
        </div>
        {flat.length === 0 && (
          <p className="search-empty" role="status">
            Nothing matches that. Try a course code, the title of an assignment or a page.
          </p>
        )}
        {!phone && (
          <p className="search-help" aria-hidden="true">
            <span>Up and down arrows to move</span>
            <span>Enter to open</span>
            <span>Esc to close</span>
          </p>
        )}
      </div>
    </div>
  );
}

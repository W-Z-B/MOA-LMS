import { useEffect, useRef, useState } from "react";
import { errorMessage, get, post, remove } from "../../api/client";
import type { CalendarEvent, CalendarFeed, EventKind } from "../../api/types-talk";
import { dmyTime, longDate } from "../../app/format";
import { usePhone } from "../../app/frame";
import { clock } from "../forums/shared";
import "../talk.css";

interface Props {
  onNavigate: (to: string) => void;
}

const KIND: Record<EventKind, string> = {
  assignment_due: "Due",
  quiz_closes: "Quiz closes",
  practical_closes: "Practical closes",
  class_session: "Class",
  release: "Released",
};

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const AGENDA_DAYS = 28;

/** A day as "2026-10-05" in the device's time. */
const dayOf = (at: Date) => `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, "0")}-${String(at.getDate()).padStart(2, "0")}`;
const startOfDay = (at: Date) => new Date(at.getFullYear(), at.getMonth(), at.getDate());
const addDays = (at: Date, days: number) => new Date(at.getFullYear(), at.getMonth(), at.getDate() + days);

/** The private feed for a phone's calendar (item 2.32): copy, make a new address, or turn it off. */
function Feed() {
  const [feed, setFeed] = useState<CalendarFeed | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => {
    get<CalendarFeed>("/calendar/feed/")
      .then(setFeed)
      .catch((err) => setError(errorMessage(err, "Could not read your calendar feed.")));
  }, []);

  async function make() {
    try {
      setFeed(await post<CalendarFeed>("/calendar/feed/"));
      setConfirming(false);
      setMessage(feed?.url ? "A new address is made. The old one has stopped working: add the new one to your phone." : "Your address is made. Add it to your phone's calendar.");
      setError(null);
    } catch (err) {
      setError(errorMessage(err, "Could not make the address."));
    }
  }

  async function turnOff() {
    try {
      await remove("/calendar/feed/");
      setFeed({ url: null, created_at: null, last_used_at: null });
      setMessage("Your calendar feed is off. The address no longer works.");
    } catch (err) {
      setError(errorMessage(err, "Could not turn the feed off."));
    }
  }

  async function copy() {
    if (!feed?.url) return;
    try {
      await navigator.clipboard.writeText(feed.url);
      setMessage("Copied. Paste it into your phone's calendar as a subscription.");
    } catch {
      // No clipboard here (an older browser, or no permission): select the address for the person to copy.
      field.current?.focus();
      field.current?.select();
      setMessage("The address is selected: copy it with Ctrl C, or press and hold on a phone.");
    }
  }

  return (
    <section className="module" aria-labelledby="feed-title">
      <h2 id="feed-title" className="talk-form-title">
        Your calendar on your phone
      </h2>
      <p className="muted small">
        A private address your phone's calendar subscribes to. It shows titles, times and places, never marks or messages. Anyone with
        the address can read it, so keep it to yourself.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {feed && !feed.url && <button onClick={make}>Make my private address</button>}
      {feed?.url && (
        <>
          <label>
            Your private address
            <input ref={field} readOnly value={feed.url} onFocus={(e) => e.target.select()} />
          </label>
          <p className="muted small">
            Made {dmyTime(feed.created_at!)}
            {feed.last_used_at ? ` · last read by a calendar ${dmyTime(feed.last_used_at)}` : " · not read by a calendar yet"}
          </p>
          <div className="actions">
            <button onClick={copy}>Copy address</button>
            {!confirming ? (
              <button className="secondary" onClick={() => setConfirming(true)}>
                Make a new address
              </button>
            ) : (
              <button className="secondary" onClick={make}>
                Make it: the old address stops working
              </button>
            )}
            <button className="secondary danger-text" onClick={turnOff}>
              Turn off
            </button>
          </div>
        </>
      )}
      {message && (
        <p role="status" className="notice good">
          {message}
        </p>
      )}
    </section>
  );
}

function EventRow({ event, onNavigate }: { event: CalendarEvent; onNavigate: (to: string) => void }) {
  return (
    <li className={`event event-${event.kind}`}>
      <span className="event-time">{event.kind === "release" ? "" : clock(event.starts_at)}</span>
      <span className="talk-row-main">
        <a
          className="talk-title"
          href={`#${event.link}`}
          onClick={(e) => {
            e.preventDefault();
            onNavigate(event.link);
          }}
        >
          {event.title}
        </a>
        <span className="muted small">
          {KIND[event.kind]} · {event.site_code}
          {event.location ? ` · ${event.location}` : ""}
        </span>
        {event.meeting_url && (
          <a className="small" href={event.meeting_url} target="_blank" rel="noopener noreferrer">
            Join online
          </a>
        )}
      </span>
    </li>
  );
}

/**
 * The calendar (#/calendar, item 2.32): due dates, classes and release dates across the person's courses, as a
 * month or as an agenda (the agenda first on a phone), filtered by course; and the private feed.
 */
export function CalendarScreen({ onNavigate }: Props) {
  const phone = usePhone();
  const [view, setView] = useState<"month" | "agenda">(phone ? "agenda" : "month");
  const [anchor, setAnchor] = useState(() => startOfDay(new Date()));
  const [loaded, setLoaded] = useState<{ period: string; events: CalendarEvent[] } | null>(null);
  const [course, setCourse] = useState("");
  const [chosenDay, setChosenDay] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const monthStart = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const from = view === "month" ? monthStart : anchor;
  const to = view === "month" ? new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1) : addDays(anchor, AGENDA_DAYS);
  const fromIso = from.toISOString();
  const toIso = to.toISOString();

  const period = `${fromIso}/${toIso}`;
  // What was read for another period is not shown: the page says it is loading until the new one arrives.
  const events = loaded?.period === period ? loaded.events : null;

  useEffect(() => {
    get<CalendarEvent[]>(`/calendar/?from=${encodeURIComponent(fromIso)}&to=${encodeURIComponent(toIso)}`)
      .then((list) => {
        setLoaded({ period: `${fromIso}/${toIso}`, events: list });
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load your calendar.")));
  }, [fromIso, toIso]);

  const courses = Array.from(new Set((events ?? []).map((e) => e.site_code))).sort();
  const shown = (events ?? []).filter((e) => !course || e.site_code === course).sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  const byDay = new Map<string, CalendarEvent[]>();
  shown.forEach((e) => {
    const day = dayOf(new Date(e.starts_at));
    byDay.set(day, [...(byDay.get(day) ?? []), e]);
  });

  const move = (step: number) => {
    setChosenDay(null);
    setAnchor(view === "month" ? new Date(anchor.getFullYear(), anchor.getMonth() + step, 1) : addDays(anchor, step * AGENDA_DAYS));
  };
  const title =
    view === "month"
      ? `${MONTHS[anchor.getMonth()]} ${anchor.getFullYear()}`
      : `${longDate(dayOf(from))} to ${longDate(dayOf(addDays(to, -1)))}`;
  const today = dayOf(new Date());

  // The month's grid, Monday first, with the days of the months either side to fill the weeks.
  const lead = (monthStart.getDay() + 6) % 7;
  const daysInMonth = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0).getDate();
  const cells = Array.from({ length: Math.ceil((lead + daysInMonth) / 7) * 7 }, (_, i) => addDays(monthStart, i - lead));
  const chosen = chosenDay ? (byDay.get(chosenDay) ?? []) : [];

  return (
    <>
      <div className="page-head">
        <h1>Calendar</h1>
        <div className="actions" role="group" aria-label="View">
          <button className={view === "month" ? "" : "secondary"} aria-pressed={view === "month"} onClick={() => setView("month")}>
            Month
          </button>
          <button className={view === "agenda" ? "" : "secondary"} aria-pressed={view === "agenda"} onClick={() => setView("agenda")}>
            Agenda
          </button>
        </div>
      </div>
      <div className="filters calendar-bar">
        <button className="secondary" onClick={() => move(-1)} aria-label={view === "month" ? "Previous month" : "Earlier"}>
          ‹
        </button>
        <h2 className="calendar-title" aria-live="polite">
          {title}
        </h2>
        <button className="secondary" onClick={() => move(1)} aria-label={view === "month" ? "Next month" : "Later"}>
          ›
        </button>
        <button
          className="secondary"
          onClick={() => {
            setChosenDay(null);
            setAnchor(startOfDay(new Date()));
          }}
        >
          Today
        </button>
        <label className="calendar-course">
          Course
          <select value={course} onChange={(e) => setCourse(e.target.value)}>
            <option value="">All courses</option>
            {courses.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {events === null && !error && <p className="loading">Loading your calendar…</p>}

      {events !== null && view === "agenda" && (
        <div className="agenda">
          {byDay.size === 0 && <p className="muted">Nothing on your calendar for these four weeks.</p>}
          {Array.from(byDay.entries()).map(([day, list]) => (
            <section key={day} aria-labelledby={`day-${day}`}>
              <h3 id={`day-${day}`} className={day === today ? "agenda-day today" : "agenda-day"}>
                {day === today ? `Today, ${longDate(day)}` : longDate(day)}
              </h3>
              <ul className="events">
                {list.map((e) => (
                  <EventRow key={`${e.kind}-${e.id}`} event={e} onNavigate={onNavigate} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {events !== null && view === "month" && (
        <>
          <div className="month" role="grid" aria-label={title}>
            <div className="month-row" role="row">
              {WEEKDAYS.map((d) => (
                <span key={d} role="columnheader" className="month-head">
                  {d}
                </span>
              ))}
            </div>
            {Array.from({ length: cells.length / 7 }, (_, week) => (
              <div className="month-row" role="row" key={week}>
                {cells.slice(week * 7, week * 7 + 7).map((date) => {
                  const day = dayOf(date);
                  const list = byDay.get(day) ?? [];
                  const inMonth = date.getMonth() === anchor.getMonth();
                  return (
                    <span role="gridcell" key={day} className={inMonth ? "month-cell" : "month-cell other"}>
                      <button
                        className={["month-day", day === today ? "today" : "", day === chosenDay ? "chosen" : ""].join(" ").trim()}
                        aria-pressed={day === chosenDay}
                        aria-label={`${longDate(day)}: ${list.length === 0 ? "nothing" : `${list.length} on the calendar`}`}
                        onClick={() => setChosenDay(day === chosenDay ? null : day)}
                      >
                        <span className="month-date">{date.getDate()}</span>
                        {list.length > 0 && (
                          <span className="month-items" aria-hidden="true">
                            {phone ? (
                              <span className="month-dot">{list.length}</span>
                            ) : (
                              list.slice(0, 2).map((e) => (
                                <span key={`${e.kind}-${e.id}`} className={`month-item event-${e.kind}`}>
                                  {e.title}
                                </span>
                              ))
                            )}
                            {!phone && list.length > 2 && <span className="month-more">{list.length - 2} more</span>}
                          </span>
                        )}
                      </button>
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
          {chosenDay && (
            <section aria-labelledby="chosen-day" className="chosen-day">
              <h3 id="chosen-day" className="agenda-day">
                {longDate(chosenDay)}
              </h3>
              {chosen.length === 0 ? (
                <p className="muted">Nothing on this day.</p>
              ) : (
                <ul className="events">
                  {chosen.map((e) => (
                    <EventRow key={`${e.kind}-${e.id}`} event={e} onNavigate={onNavigate} />
                  ))}
                </ul>
              )}
            </section>
          )}
        </>
      )}
      <Feed />
    </>
  );
}

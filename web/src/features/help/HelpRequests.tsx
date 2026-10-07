import { useCallback, useEffect, useState } from "react";
import { errorMessage, get, post } from "../../api/client";
import { ADMIN_ROLES, hasAnyRole, type Me } from "../../api/types";
import type { HelpRequest } from "../../api/types-help";
import { dmyTime } from "../../app/format";
import { useCrumb, useFrame } from "../../app/frame";
import "./help.css";

type Show = "open" | "answered" | "mine";
const QUERY: Record<Show, string> = { open: "?status=open", answered: "?status=answered", mine: "?mine=1" };
const SHOW: Record<Show, string> = { open: "Waiting", answered: "Answered", mine: "Mine" };

/** Written on a phone without signal and sent later: more than two minutes between writing and arriving. */
const waited = (row: HelpRequest) =>
  row.client_sent_at !== null && new Date(row.created_at).getTime() - new Date(row.client_sent_at).getTime() > 120_000;

interface Props {
  me: Me;
  /** A request to bring into view, from a notification or To do: #/help/requests/12. */
  focus: number | null;
  onNavigate: (to: string) => void;
}

/**
 * Help requests (item 7.17). Course administrators and administrators see every request, read the page the
 * person was on, and answer; the answer goes to the person as a notification. Everyone else sees their own
 * requests and the answers.
 */
export function HelpRequests({ me, focus, onNavigate }: Props) {
  const answerer = hasAnyRole(me, ADMIN_ROLES);
  const [show, setShow] = useState<Show>(answerer ? "open" : "mine");
  const [rows, setRows] = useState<HelpRequest[] | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { decided } = useFrame();
  useCrumb(answerer ? "Help requests" : "My help requests");

  const load = useCallback(() => {
    get<HelpRequest[]>(`/help-requests/${QUERY[show]}`)
      .then(setRows)
      .catch((err) => setError(errorMessage(err, "Could not read the help requests.")));
  }, [show]);
  useEffect(load, [load]);

  useEffect(() => {
    if (focus === null || rows === null) return;
    document.getElementById(`help-request-${focus}`)?.scrollIntoView?.({ block: "start" });
  }, [focus, rows]);

  async function answer(row: HelpRequest) {
    setError(null);
    try {
      await post(`/help-requests/${row.id}/answer/`, { answer: answers[row.id] ?? "" });
      setStatus(`Your answer to “${row.subject}” is sent.`);
      decided();
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not send the answer."));
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>{answerer ? "Help requests" : "My help requests"}</h1>
        <a
          className="button-like"
          href="#/help/ask"
          onClick={(e) => {
            e.preventDefault();
            onNavigate("/help/ask");
          }}
        >
          Ask for help
        </a>
      </div>
      {answerer && (
        <div className="filters" role="group" aria-label="Show">
          {(["open", "answered", "mine"] as const).map((s) => (
            <button key={s} type="button" className={show === s ? "small-button" : "secondary small-button"} aria-pressed={show === s} onClick={() => setShow(s)}>
              {SHOW[s]}
            </button>
          ))}
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p role="status" className={status ? "notice good" : "sr-only"}>
        {status}
      </p>
      {rows === null && !error && <p className="loading">Reading the help requests…</p>}
      {rows?.length === 0 && <p className="muted">{show === "open" ? "No help request is waiting for an answer." : "No help requests yet."}</p>}
      <ul className="plain help-requests">
        {rows?.map((row) => (
          <li key={row.id} id={`help-request-${row.id}`} className={row.id === focus ? "panel-card padded focus" : "panel-card padded"}>
            <h2 className="item-title">{row.subject}</h2>
            <p className="muted small">
              {row.mine ? "You asked" : `From ${row.asked_by_name ?? "someone no longer here"}`} on {dmyTime(row.created_at)}
              {row.status === "open" ? " · Waiting for an answer" : " · Answered"}
              {waited(row) && ` · Written on the phone on ${dmyTime(row.client_sent_at!)}`}
            </p>
            <p className="help-message">{row.message}</p>
            {row.page && (
              <p className="small">
                <a href={`#${row.page}`}>{row.mine ? "Open the page I was on" : "Open the page they were on"}</a>
              </p>
            )}
            {row.status === "answered" ? (
              <div className="help-answer">
                <p className="muted small">
                  Answered by {row.answered_by_name ?? "a course administrator"}
                  {row.answered_at ? ` on ${dmyTime(row.answered_at)}` : ""}
                </p>
                <p className="help-message">{row.answer}</p>
              </div>
            ) : (
              answerer &&
              !row.mine && (
                <div className="help-form">
                  <label>
                    Your answer
                    <textarea rows={4} value={answers[row.id] ?? ""} onChange={(e) => setAnswers((prev) => ({ ...prev, [row.id]: e.target.value }))} />
                  </label>
                  <div>
                    <button type="button" disabled={!(answers[row.id] ?? "").trim()} onClick={() => answer(row)}>
                      Send the answer
                    </button>
                  </div>
                </div>
              )
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

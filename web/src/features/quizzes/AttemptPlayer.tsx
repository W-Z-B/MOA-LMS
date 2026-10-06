import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, errorMessage, get, post } from "../../api/client";
import type { AnswerSaved, Attempt, AttemptQuestion } from "../../api/types-quizzes";
import { flush, pending, saveQuizAnswer } from "../../app/offlineQueue";
import { SendState } from "../../app/SendState";
import { AnswerInput } from "./AnswerInput";
import { Countdown } from "./Countdown";
import { isAnswered } from "./describe";
import { Review } from "./Review";
import { Rich } from "./Rich";

type Resp = Record<string, unknown>;

/** Beside each question: what happened to its last answer. A write kept on the device shows SendState. */
type Sending = { state: "saving" } | { state: "sent" } | { state: "queued"; id: string } | { state: "error"; detail: string };

const TYPING_PAUSE_MS = 800;

interface Props {
  attemptId: number;
  onBack: () => void;
}

/**
 * Answering an attempt (items 3.03 and 4.02). Each answer is saved as it is given, through the offline queue,
 * so an answer given without signal waits on the device and is sent when the connection returns. Time is the
 * server's: the countdown starts from the seconds the server says are left, and is set again on reconnecting.
 */
export function AttemptPlayer({ attemptId, onBack }: Props) {
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [responses, setResponses] = useState<Record<number, Resp | null>>({});
  const [sending, setSending] = useState<Record<number, Sending>>({});
  const [page, setPage] = useState(1);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Why the attempt ended without the student submitting it: time ran out. */
  const [ended, setEnded] = useState<string | null>(null);
  const [sync, setSync] = useState<{ seconds: number; at: number } | null>(null);
  const typing = useRef(new Map<number, { timer: number; response: Resp }>());
  const top = useRef<HTMLParagraphElement>(null);
  const confirmHead = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (confirming) confirmHead.current?.focus();
  }, [confirming]);

  const take = useCallback((a: Attempt) => {
    setAttempt(a);
    setResponses((current) => {
      const next: Record<number, Resp | null> = {};
      // Keep what is being typed or waits on the device; take the server's answer for the rest.
      for (const q of a.questions) next[q.position] = typing.current.has(q.position) ? current[q.position] : (current[q.position] ?? q.response);
      return next;
    });
    if (a.navigation === "sequential") setPage(a.current_page);
    setSync(a.seconds_left === null ? null : { seconds: a.seconds_left, at: Date.now() });
  }, []);

  const load = useCallback(() => {
    get<Attempt>(`/quiz-attempts/${attemptId}/`)
      .then((a) => {
        take(a);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not open the attempt.")));
  }, [attemptId, take]);

  useEffect(load, [load]);

  // Back online: answers kept on the device are sent, and the time left is read again from the server.
  useEffect(() => {
    const online = () => {
      void flush().then(load);
    };
    window.addEventListener("online", online);
    return () => window.removeEventListener("online", online);
  }, [load]);

  const save = useCallback(
    async (q: AttemptQuestion, response: Resp, title: string) => {
      setSending((s) => ({ ...s, [q.position]: { state: "saving" } }));
      try {
        const sent = await saveQuizAnswer<AnswerSaved>(attemptId, q.position, response, `Answer to question ${q.position} of ${title}`);
        if (sent.queued) {
          setSending((s) => ({ ...s, [q.position]: { state: "queued", id: sent.item.id } }));
          return;
        }
        setSending((s) => ({ ...s, [q.position]: { state: "sent" } }));
        if (sent.result.seconds_left !== null) setSync({ seconds: sent.result.seconds_left, at: Date.now() });
      } catch (err) {
        if (err instanceof ApiError && (err.code === "time_up" || err.code === "finished")) {
          setEnded(err.detail);
          load();
          return;
        }
        setSending((s) => ({ ...s, [q.position]: { state: "error", detail: errorMessage(err, "Not saved.") } }));
      }
    },
    [attemptId, load],
  );

  /** Send whatever is still being typed now, rather than after the pause. */
  const sendTyped = useCallback(async () => {
    if (!attempt) return;
    const waiting = [...typing.current.entries()];
    typing.current.clear();
    await Promise.all(
      waiting.map(([position, entry]) => {
        window.clearTimeout(entry.timer);
        const q = attempt.questions.find((x) => x.position === position);
        return q ? save(q, entry.response, attempt.quiz_title) : undefined;
      }),
    );
  }, [attempt, save]);

  useEffect(() => () => typing.current.forEach((t) => window.clearTimeout(t.timer)), []);

  const submit = useCallback(
    async (auto = false) => {
      if (!attempt) return;
      setSubmitting(true);
      setError(null);
      try {
        await sendTyped();
        await flush();
        const mine = `/quiz-attempts/${attemptId}/`;
        if (pending().some((item) => item.path.startsWith(mine))) {
          setError(
            auto
              ? "Time is up, and some answers are still waiting to send. They are sent, and the attempt is submitted, when the connection returns."
              : "Some answers are still waiting to send. Submit when the connection returns.",
          );
          return;
        }
        take(await post<Attempt>(`${mine}submit/`));
        setConfirming(false);
      } catch (err) {
        setError(err instanceof TypeError ? "No connection. Submit when the connection returns." : errorMessage(err, "Could not submit."));
      } finally {
        setSubmitting(false);
      }
    },
    [attempt, attemptId, sendTyped, take],
  );

  const expire = useCallback(() => void submit(true), [submit]);

  if (error && !attempt)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!attempt) return <p className="loading">Opening the attempt…</p>;

  if (attempt.state === "finished")
    return (
      <>
        <BackLink onBack={onBack} />
        <h2>{attempt.quiz_title}</h2>
        {ended && <p className="notice">{ended}</p>}
        <Review attempt={attempt} />
      </>
    );

  const pages = [...new Set(attempt.questions.map((q) => q.page))].sort((a, b) => a - b);
  const current = attempt.navigation === "sequential" ? attempt.current_page : page;
  const shown = attempt.questions.filter((q) => q.page === current);
  const lastPage = current >= attempt.last_page;
  const unanswered = attempt.questions.filter((q) => !isAnswered(q.qtype, responses[q.position] ?? null)).length;

  function change(q: AttemptQuestion, response: Resp, isTyping = false) {
    setResponses((r) => ({ ...r, [q.position]: response }));
    const held = typing.current.get(q.position);
    if (held) window.clearTimeout(held.timer);
    if (!isTyping) {
      typing.current.delete(q.position);
      void save(q, response, attempt!.quiz_title);
      return;
    }
    const timer = window.setTimeout(() => {
      typing.current.delete(q.position);
      void save(q, response, attempt!.quiz_title);
    }, TYPING_PAUSE_MS);
    typing.current.set(q.position, { timer, response });
  }

  async function upload(q: AttemptQuestion, file: File) {
    setSending((s) => ({ ...s, [q.position]: { state: "saving" } }));
    const body = new FormData();
    body.set("file", file);
    try {
      await post(`/quiz-attempts/${attemptId}/answers/${q.position}/file/`, body);
      setResponses((r) => ({ ...r, [q.position]: { filename: file.name } }));
      setSending((s) => ({ ...s, [q.position]: { state: "sent" } }));
    } catch (err) {
      const detail = err instanceof TypeError ? "No connection. Choose the file again when you are back online." : errorMessage(err, "Not uploaded.");
      setSending((s) => ({ ...s, [q.position]: { state: "error", detail } }));
    }
  }

  async function goTo(next: number) {
    setError(null);
    if (attempt!.navigation === "sequential") {
      await sendTyped();
      await flush();
      try {
        take(await post<Attempt>(`/quiz-attempts/${attemptId}/next-page/`));
      } catch (err) {
        setError(err instanceof TypeError ? "No connection. Move on when the connection returns." : errorMessage(err, "Could not move on."));
        return;
      }
    } else setPage(next);
    top.current?.focus();
  }

  return (
    <>
      <BackLink onBack={onBack} />
      <div className="attempt-head">
        <h2>{attempt.quiz_title}</h2>
        {sync && <Countdown secondsLeft={sync.seconds} syncedAt={sync.at} onExpire={expire} />}
      </div>
      {attempt.last_page > 1 && (
        <p className="muted page-of" ref={top} tabIndex={-1}>
          Page {current} of {attempt.last_page}
          {attempt.navigation === "sequential" && ". You cannot go back to an earlier page."}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {shown.map((q) => (
        <section key={q.position} className="module question" aria-labelledby={`q${q.position}-head`}>
          <div className="panel-head">
            <h3 id={`q${q.position}-head`}>Question {q.position}</h3>
            <span className="muted small">
              {Number(q.max_mark)} {Number(q.max_mark) === 1 ? "mark" : "marks"}
            </span>
          </div>
          {q.qtype !== "cloze" && <Rich html={q.text} />}
          {q.image_url && q.qtype !== "image_label" && <img className="question-image" src={q.image_url} alt={`Picture for question ${q.position}`} />}
          <AnswerInput q={q} value={responses[q.position] ?? null} onChange={(r, isTyping) => change(q, r, isTyping)} onFile={(f) => void upload(q, f)} />
          <SendMark sending={sending[q.position]} />
        </section>
      ))}
      {confirming ? (
        <section className="module confirm" aria-labelledby="confirm-head">
          <h3 id="confirm-head" ref={confirmHead} tabIndex={-1}>
            Submit your answers?
          </h3>
          <p>
            {unanswered === 0
              ? "You have answered every question."
              : `${unanswered} of ${attempt.questions.length} questions ${unanswered === 1 ? "has" : "have"} no answer.`}{" "}
            Once submitted, your answers cannot be changed.
          </p>
          <div className="actions">
            <button onClick={() => void submit()} disabled={submitting}>
              {submitting ? "Submitting…" : "Submit my answers"}
            </button>
            <button className="secondary" onClick={() => setConfirming(false)} disabled={submitting}>
              Back to the questions
            </button>
          </div>
        </section>
      ) : (
        <div className="actions attempt-nav">
          {attempt.navigation === "free" && current > pages[0] && (
            <button className="secondary" onClick={() => void goTo(pages[pages.indexOf(current) - 1])}>
              Previous page
            </button>
          )}
          {!lastPage && <button onClick={() => void goTo(pages[pages.indexOf(current) + 1])}>Next page</button>}
          {(lastPage || attempt.navigation === "free") && (
            <button className={lastPage ? undefined : "secondary"} onClick={() => setConfirming(true)}>
              Finish attempt…
            </button>
          )}
        </div>
      )}
    </>
  );
}

function SendMark({ sending }: { sending?: Sending }) {
  if (!sending) return null;
  if (sending.state === "queued") return <SendState id={sending.id} />;
  if (sending.state === "saving")
    return <span className="sync waiting">Saving…</span>;
  if (sending.state === "sent")
    return (
      <span role="status" className="sync sent">
        Sent
      </span>
    );
  return (
    <span role="alert" className="sync refused">
      Not saved: {sending.detail}
    </span>
  );
}

export function BackLink({ onBack, label = "All quizzes" }: { onBack: () => void; label?: string }) {
  return (
    <button className="link accent back-link" onClick={onBack}>
      <span aria-hidden="true">← </span>
      {label}
    </button>
  );
}

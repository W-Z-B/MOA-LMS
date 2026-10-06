import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { Paginated } from "../../api/types";
import { NoticeText } from "./PrivacyNoticeScreen";
import { SUBJECTS, type Correction, type CurrentNotice, type OwnRecord } from "./types";

type Row = Record<string, string | number | boolean | null>;
type Column = [key: string, label: string];

const DATE_KEYS = new Set(["at", "since", "sent_at", "read_at", "submitted_at", "completed_on", "given"]);

function shown(key: string, value: Row[string]): string {
  if (value === null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (DATE_KEYS.has(key) && typeof value === "string") return new Date(value).toLocaleString("en-GB");
  return String(value);
}

/** A small table that scrolls sideways on a phone rather than widening the page. */
function Table({ rows, columns, empty, limit = 50 }: { rows: Row[]; columns: Column[]; empty: string; limit?: number }) {
  if (rows.length === 0) return <p className="muted">{empty}</p>;
  return (
    // A region that can take focus, so the table can be scrolled sideways from a keyboard too (item 4.01).
    <div className="scroll-x" tabIndex={0} role="region" aria-label={`Table: ${columns.map(([, label]) => label).join(", ")}`}>
      <table>
        <thead>
          <tr>
            {columns.map(([key, label]) => (
              <th key={key}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, limit).map((row, i) => (
            <tr key={i}>
              {columns.map(([key]) => (
                <td key={key}>{shown(key, row[key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > limit && (
        <p className="muted small">
          Showing {limit} of {rows.length}. The downloaded file has them all.
        </p>
      )}
    </div>
  );
}

/** My data (item 1.18): what the LMS holds about me, to read and download, and corrections to ask for. */
export function MyDataScreen() {
  const [data, setData] = useState<OwnRecord | null>(null);
  const [corrections, setCorrections] = useState<Correction[]>([]);
  const [notice, setNotice] = useState<CurrentNotice | null>(null);
  const [showNotice, setShowNotice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ subject: "mark", wrong: "", should_be: "" });
  const [sent, setSent] = useState<string | null>(null);

  function loadCorrections() {
    get<Paginated<Correction>>("/privacy/corrections/")
      .then((r) => setCorrections(r.results))
      .catch(() => setCorrections([]));
  }

  useEffect(() => {
    get<OwnRecord>("/privacy/my-record/")
      .then(setData)
      .catch((err) => setError(errorMessage(err, "Could not load your data.")));
    get<CurrentNotice>("/privacy/notice/")
      .then(setNotice)
      .catch(() => setNotice(null));
    loadCorrections();
  }, []);

  async function ask(e: FormEvent) {
    e.preventDefault();
    setSent(null);
    try {
      await post("/privacy/corrections/", form);
      setForm((prev) => ({ ...prev, wrong: "", should_be: "" }));
      setSent("Your request has been sent. A course administrator will answer it.");
      loadCorrections();
    } catch (err) {
      setSent(errorMessage(err, "Could not send your request."));
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="loading">Loading your data…</p>;
  const person = data.person;

  return (
    <>
      <div className="panel-head" style={{ flexWrap: "wrap" }}>
        <div>
          <h1>My data</h1>
          <p className="muted">{data.about}</p>
        </div>
        <button type="button" onClick={() => (window.location.href = "/api/v1/privacy/my-record/download/")}>
          Download my data
        </button>
      </div>

      {person && (
        <div className="panel">
          <dl>
            <dt>Name</dt>
            <dd>{`${person.first_name} ${person.last_name}`.trim() || "—"}</dd>
            <dt>{person.kind}</dt>
            <dd>{person.number}</dd>
            <dt>Email</dt>
            <dd className="wrap">{person.email || "—"}</dd>
            <dt>Campus</dt>
            <dd>{person.campus || "—"}</dd>
          </dl>
        </div>
      )}

      {person && (
        <>
          <h2>Courses</h2>
          <Table
            rows={person.memberships}
            columns={[["site", "Course"], ["title", "Title"], ["term", "Term"], ["role", "Role"], ["active", "Active"]]}
            empty="You do not belong to any course."
          />
        </>
      )}
      {person?.submissions && (
        <>
          <h2>Submissions</h2>
          <Table
            rows={person.submissions}
            columns={[["site", "Course"], ["assignment", "Assignment"], ["submitted_at", "Submitted"], ["late", "Late"], ["file", "File"]]}
            empty="You have not submitted any work."
          />
          <h2>Marks released to you</h2>
          <Table
            rows={person.released_marks ?? []}
            columns={[["site", "Course"], ["assignment", "Assignment"], ["mark", "Mark"], ["out_of", "Out of"], ["feedback", "Feedback"]]}
            empty="No marks have been released to you yet."
          />
        </>
      )}
      {person && (
        <>
          <h2>Courses completed</h2>
          <Table rows={person.completions} columns={[["site", "Course"], ["title", "Title"], ["completed_on", "Completed"]]} empty="None yet." />
        </>
      )}
      {data.teaching_actions && (
        <>
          <h2>What I did in the LMS</h2>
          <Table
            rows={data.teaching_actions}
            columns={[["at", "When"], ["action", "What"], ["record", "Record"], ["reason", "Reason"]]}
            empty="Nothing recorded yet."
          />
        </>
      )}
      {data.account && (
        <>
          <h2>Sign-ins</h2>
          <Table rows={data.account.sign_ins} columns={[["at", "When"], ["what", "What"], ["from", "From"]]} empty="None recorded." limit={20} />
          <p className="muted small">
            The LMS records sign-ins, downloads and submissions only. It does not record how long you spend on a page.
          </p>
        </>
      )}

      <h2>Ask for a correction</h2>
      <form className="stack panel" onSubmit={ask}>
        <label htmlFor="corr-subject">
          What is it about
          <select id="corr-subject" value={form.subject} onChange={(e) => setForm((prev) => ({ ...prev, subject: e.target.value }))}>
            {SUBJECTS.map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="corr-wrong">
          What is wrong
          <textarea id="corr-wrong" required maxLength={1000} value={form.wrong} onChange={(e) => setForm((prev) => ({ ...prev, wrong: e.target.value }))} />
        </label>
        <label htmlFor="corr-should">
          What it should say
          <textarea id="corr-should" required maxLength={1000} value={form.should_be} onChange={(e) => setForm((prev) => ({ ...prev, should_be: e.target.value }))} />
        </label>
        <div>
          <button type="submit">Send the request</button>
        </div>
        {sent && <p className="notice">{sent}</p>}
      </form>
      {corrections.length > 0 && (
        <Table
          rows={corrections.map((c) => ({ about: c.subject_name, wrong: c.wrong, state: c.state_name, answer: c.decision_note }))}
          columns={[["about", "About"], ["wrong", "What is wrong"], ["state", "State"], ["answer", "Answer"]]}
          empty=""
        />
      )}

      {notice?.notice && (
        <>
          <h2>Privacy notice</h2>
          <button className="link" onClick={() => setShowNotice(!showNotice)}>
            {showNotice ? "Hide" : "Read"} the privacy notice (version {notice.notice.version})
          </button>
          {showNotice && (
            <div className="panel">
              <NoticeText notice={notice.notice} />
            </div>
          )}
        </>
      )}
    </>
  );
}

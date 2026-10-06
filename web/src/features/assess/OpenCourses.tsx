import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, errorMessage, get, post } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { OpenCatalogue, OpenCourse } from "../../api/types-assess";
import { dmy } from "../../app/format";
import { AuthFrame } from "../auth/AuthFrame";
import { PASSWORD_RULES } from "../auth/SetPasswordScreen";
import "./assess.css";

/** What the catalogue says when GSA has not switched open courses on (OPEN_COURSES_ENABLED, ADR 0032). */
const OFF = "GSA does not offer open short courses at present.";

function useCatalogue() {
  const [catalogue, setCatalogue] = useState<OpenCatalogue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    get<OpenCatalogue>("/open-courses/")
      .then((c) => {
        setCatalogue(c);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError && err.code === "open_courses_off" ? OFF : errorMessage(err, "Could not load the courses.")));
  }, []);
  useEffect(load, [load]);
  return { catalogue, error, load };
}

function CourseFacts({ course }: { course: OpenCourse }) {
  const facts = [
    course.audience && `For ${course.audience.charAt(0).toLowerCase()}${course.audience.slice(1)}`,
    course.length_hours && `about ${course.length_hours} hours`,
    course.places_left !== null && (course.places_left > 0 ? `${course.places_left} place${course.places_left === 1 ? "" : "s"} left` : "full"),
    course.certificate && "certificate on completion",
  ].filter(Boolean);
  return (
    <>
      <h3>{course.title}</h3>
      {course.summary && <p>{course.summary}</p>}
      {facts.length > 0 && <p className="muted small">{facts.join(" · ")}</p>}
    </>
  );
}

/**
 * The public page of open short courses for farmers and extension officers (item 5.07): the courses, and
 * registration by email with the privacy notice read and accepted. Nothing is made until the emailed link
 * is followed. Off unless GSA switches it on.
 */
export function PublicOpenCourses() {
  const { catalogue, error } = useCatalogue();
  const [draft, setDraft] = useState({ first_name: "", last_name: "", email: "", site: "", privacy_accepted: false });
  const [done, setDone] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function register(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      const answer = await post<{ detail: string }>("/open-courses/register/", { ...draft, site: draft.site ? Number(draft.site) : null });
      setDone(answer.detail);
    } catch (err) {
      setProblem(errorMessage(err, "Could not send the registration."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <div className="card stack">
        <h1 className="card-eyebrow">GSA short courses</h1>
        <h2>Short courses for farmers and extension officers</h2>
        {error && <p className={error === OFF ? "notice" : "error"} role={error === OFF ? undefined : "alert"}>{error}</p>}
        {catalogue && catalogue.courses.length === 0 && <p className="muted">No short course is open just now.</p>}
        {catalogue?.courses.map((course) => (
          <section key={course.id} className="course-card key-card" aria-label={course.title}>
            <CourseFacts course={course} />
          </section>
        ))}
        {catalogue && (
          <form className="stack" onSubmit={register} aria-labelledby="register-heading">
            <h2 id="register-heading">Register</h2>
            {done ? (
              <p role="status" className="notice good">
                {done} Follow the link in the email to choose your password.
              </p>
            ) : (
              <>
                <label>
                  First name
                  <input autoComplete="given-name" value={draft.first_name} onChange={(e) => setDraft({ ...draft, first_name: e.target.value })} required maxLength={80} />
                </label>
                <label>
                  Last name
                  <input autoComplete="family-name" value={draft.last_name} onChange={(e) => setDraft({ ...draft, last_name: e.target.value })} required maxLength={80} />
                </label>
                <label>
                  Email address
                  <input type="email" autoComplete="email" value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} required />
                </label>
                <label>
                  Course to join
                  <select value={draft.site} onChange={(e) => setDraft({ ...draft, site: e.target.value })}>
                    <option value="">Choose later</option>
                    {catalogue.courses
                      .filter((c) => c.places_left !== 0)
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.title}
                        </option>
                      ))}
                  </select>
                </label>
                {catalogue.privacy_notice && (
                  <div>
                    <p className="strong">{catalogue.privacy_notice.title}</p>
                    <div className="notice-text" tabIndex={0} role="region" aria-label="Privacy notice">
                      {catalogue.privacy_notice.body}
                    </div>
                  </div>
                )}
                <label className="inline">
                  <input type="checkbox" checked={draft.privacy_accepted} onChange={(e) => setDraft({ ...draft, privacy_accepted: e.target.checked })} required /> I
                  have read the privacy notice and accept it
                </label>
                {problem && (
                  <p role="alert" className="error">
                    {problem}
                  </p>
                )}
                <button type="submit" className="wide" disabled={busy}>
                  Register
                </button>
              </>
            )}
            <p className="small">
              Already registered? <a href="#/">Sign in</a> with your email address.
            </p>
          </form>
        )}
      </div>
    </AuthFrame>
  );
}

/** Following the emailed link: the person chooses a password and their learner account is made. */
export function OpenConfirmScreen({ token, onDone }: { token: string; onDone: (username: string) => void }) {
  const [link, setLink] = useState<{ email: string; first_name: string; course: string | null } | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<{ email: string; first_name: string; course: string | null }>(`/open-courses/confirm/?token=${encodeURIComponent(token)}`)
      .then(setLink)
      .catch((err) => setInvalid(errorMessage(err, "Could not check the link.")));
  }, [token]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (password !== repeat) {
      setProblem("The two passwords are not the same.");
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      const made = await post<{ username: string }>("/open-courses/confirm/", { token, password });
      onDone(made.username);
    } catch (err) {
      setProblem(errorMessage(err, "Could not make the account."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <form className="card" onSubmit={submit} aria-labelledby="confirm-heading">
        <h1 className="card-eyebrow">GSA short courses</h1>
        <h2 id="confirm-heading">Finish registering</h2>
        {link === null && invalid === null && <p className="loading">Checking your link…</p>}
        {invalid !== null && (
          <>
            <p role="alert" className="error">
              {invalid}
            </p>
            <a className="button" href="#/open-courses">
              Register again
            </a>
          </>
        )}
        {link && (
          <>
            <p>
              Welcome, {link.first_name}. You will sign in with <strong>{link.email}</strong>
              {link.course ? `, and you will be on ${link.course}` : ""}.
            </p>
            <p className="muted" id="open-password-rules">
              {PASSWORD_RULES}
            </p>
            <label>
              Choose a password
              <input type="password" autoComplete="new-password" aria-describedby="open-password-rules" value={password} onChange={(e) => setPassword(e.target.value)} minLength={12} required />
            </label>
            <label>
              The password again
              <input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} required />
            </label>
            {problem && (
              <p role="alert" className="error">
                {problem}
              </p>
            )}
            <button type="submit" className="wide" disabled={busy}>
              Make my account
            </button>
          </>
        )}
      </form>
    </AuthFrame>
  );
}

interface Certificate {
  id: number;
  reference: string;
  course: string;
  issued_on: string;
  status: string;
}

/**
 * Short courses for a signed-in person (item 5.07): join one, open the ones joined, and download the
 * certificates earned.
 */
export default function OpenCoursesPage() {
  const { catalogue, error, load } = useCatalogue();
  const [certificates, setCertificates] = useState<Certificate[]>([]);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    get<Paginated<Certificate>>("/certificates/")
      .then((r) => setCertificates(r.results))
      .catch(() => setCertificates([]));
  }, []);

  async function join(course: OpenCourse) {
    setProblem(null);
    try {
      await post(`/open-courses/${course.id}/join/`);
      load();
    } catch (err) {
      setProblem(errorMessage(err, "Could not join the course."));
    }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Short courses</h1>
      </div>
      {error && <p className={error === OFF ? "notice" : "error"} role={error === OFF ? undefined : "alert"}>{error}</p>}
      {problem && (
        <p role="alert" className="error">
          {problem}
        </p>
      )}
      {catalogue?.courses.map((course) => (
        <section key={course.id} className="module course-card" aria-label={course.title}>
          <CourseFacts course={course} />
          <div className="actions">
            {course.joined ? (
              <a className="button" href={`#/sites/${course.id}`}>
                Open the course
              </a>
            ) : (
              <button type="button" disabled={course.places_left === 0} onClick={() => join(course)}>
                Join
              </button>
            )}
          </div>
        </section>
      ))}
      <section className="module" aria-labelledby="my-certificates">
        <h2 id="my-certificates">My certificates</h2>
        {certificates.length === 0 ? (
          <p className="muted">A certificate is issued here when you complete a course.</p>
        ) : (
          <ul className="plain">
            {certificates.map((c) => (
              <li key={c.id} className="item-row">
                <a href={`/api/v1/certificates/${c.id}/download/`} download>
                  {c.course}
                </a>{" "}
                <span className="muted small">
                  {c.reference}, issued {dmy(c.issued_on)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

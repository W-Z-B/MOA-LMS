import { post } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { LearningPath, PathProgress } from "../../api/types-staff";
import { useCrumb } from "../../app/frame";
import { rows, useAction, useData } from "../admin/data";
import { Said, Section } from "../admin/kit";

const STEP: Record<PathProgress["steps"][number]["state"], string> = {
  done: "Done",
  open: "Open to you",
  locked: "Opens after the one before",
};

function Bar({ progress }: { progress: PathProgress }) {
  const share = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
  return (
    <div className="bar-row">
      <div className="bar" role="img" aria-label={`${progress.done} of ${progress.total} courses done`}>
        <span style={{ width: `${share}%` }} />
      </div>
      <span className="small muted bar-summary">
        {progress.complete ? "Complete" : `${progress.done} of ${progress.total} done`}
      </span>
    </div>
  );
}

function PathRow({ path, onNavigate }: { path: LearningPath; onNavigate: (to: string) => void }) {
  const { data: progress } = useData<PathProgress>(`/staff-development/paths/${path.id}/progress/`);
  return (
    <li>
      <div className="row-head">
        <a
          className="strong"
          href={`#/learning/paths/${path.id}`}
          onClick={(e) => {
            e.preventDefault();
            onNavigate(`/learning/paths/${path.id}`);
          }}
        >
          {path.title}
        </a>
        {progress?.joined && <span className="chip chip-waiting">Following</span>}
        {!path.is_published && <span className="chip chip-draft">Not published</span>}
      </div>
      <span className="small muted">
        {[path.audience, `${path.steps.length} ${path.steps.length === 1 ? "course" : "courses"}`].filter(Boolean).join(" · ")}
      </span>
      {progress?.joined && <Bar progress={progress} />}
    </li>
  );
}

/** One path: its courses in order, each opening when the one before it is complete (item 5.04). */
function PathPage({ id, onNavigate }: { id: number; onNavigate: (to: string) => void }) {
  const { data: path, error } = useData<LearningPath>(`/staff-development/paths/${id}/`, "Could not load the path.");
  const progress = useData<PathProgress>(`/staff-development/paths/${id}/progress/`);
  const action = useAction();
  useCrumb(path?.title);

  if (error) return <Said error={error} />;
  if (!path) return <p className="loading">Loading…</p>;
  const steps = progress.data?.steps ?? path.steps.map((s) => ({ ...s, state: null, enrolled: false }));

  const join = () =>
    action.run(async () => {
      progress.setData(await post<PathProgress>(`/staff-development/paths/${id}/join/`));
      return "You are following the path. Its first course you have not completed is open to you.";
    });

  return (
    <Section title={path.title} intro={path.description}>
      {progress.data && <Bar progress={progress.data} />}
      <ol className="rows flush" aria-label="Courses on the path">
        {steps.map((step) => (
          <li key={step.site} className="row-head">
            <a
              href={`#/learning/${step.site}`}
              onClick={(e) => {
                e.preventDefault();
                onNavigate(`/learning/${step.site}`);
              }}
            >
              {step.position}. {step.title}
            </a>
            {step.state && <span className={step.state === "done" ? "chip chip-done" : "chip"}>{STEP[step.state]}</span>}
          </li>
        ))}
      </ol>
      {progress.data && !progress.data.joined && (
        <div className="actions">
          <button type="button" disabled={action.busy} onClick={join}>
            Follow this path
          </button>
        </div>
      )}
      <Said done={action.done} error={action.error} />
    </Section>
  );
}

/** Learning paths (item 5.04): courses in order for a role, with how far along each the person is. */
export function Paths({ id, onNavigate }: { id: number | null; onNavigate: (to: string) => void }) {
  const { data, error } = useData<Paginated<LearningPath>>(id === null ? "/staff-development/paths/" : null, "Could not load the paths.");
  if (id !== null) return <PathPage id={id} onNavigate={onNavigate} />;
  const paths = data ? rows(data) : null;
  return (
    <Section title="Learning paths" intro="Courses in order for a role, such as new lecturer induction. Each opens once the one before it is complete.">
      <Said error={error} />
      {paths === null && !error && <p className="loading">Loading…</p>}
      {paths !== null && paths.length === 0 && <p className="muted">There are no learning paths yet.</p>}
      {paths !== null && paths.length > 0 && (
        <ul className="rows flush" aria-label="Learning paths">
          {paths.map((path) => (
            <PathRow key={path.id} path={path} onNavigate={onNavigate} />
          ))}
        </ul>
      )}
    </Section>
  );
}

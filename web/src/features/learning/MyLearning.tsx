import { post } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { CatalogueCourse, EnrolmentRequest, TrainingAssignment } from "../../api/types-staff";
import { dmy, dmyTime } from "../../app/format";
import { rows, useAction, useData } from "../admin/data";
import { Said, Section } from "../admin/kit";
import { CourseRow } from "./Catalogue";

const REQUEST_STATE: Record<EnrolmentRequest["state"], string> = {
  submitted: "Waiting for a decision",
  approved: "Approved",
  rejected: "Not approved",
  withdrawn: "Withdrawn",
};

const TRAINING_STATE: Record<TrainingAssignment["state"], string> = { done: "Done", due: "Due", overdue: "Overdue" };

/**
 * My learning (items 5.02 to 5.05): the courses I am on or have completed, my requests to join, and the
 * training I am required to take, with when it is due.
 */
export function MyLearning({ onNavigate }: { onNavigate: (to: string) => void }) {
  const catalogue = useData<Paginated<CatalogueCourse>>("/staff-development/catalogue/", "Could not load your courses.");
  const requests = useData<Paginated<EnrolmentRequest>>("/staff-development/requests/?mine=1", "Could not load your requests.");
  const required = useData<TrainingAssignment[]>("/staff-development/required/mine/", "Could not load your required training.");
  const action = useAction();

  const mine = catalogue.data ? rows(catalogue.data).filter((c) => c.my_status && c.my_status !== "none") : null;
  const asked = requests.data ? rows(requests.data) : null;

  const withdraw = (request: EnrolmentRequest) =>
    action.run(async () => {
      await post(`/staff-development/requests/${request.id}/withdraw/`, {});
      requests.reload();
      catalogue.reload();
      return `Your request to join ${request.site_title} is withdrawn.`;
    });

  return (
    <>
      <Section title="My courses">
        <Said error={catalogue.error} />
        {mine === null && !catalogue.error && <p className="loading">Loading…</p>}
        {mine !== null && mine.length === 0 && (
          <p className="muted">You have not joined a course yet. The catalogue lists those open to you.</p>
        )}
        {mine !== null && mine.length > 0 && (
          <ul className="rows flush" aria-label="My courses">
            {mine.map((course) => (
              <CourseRow key={course.site} course={course} onNavigate={onNavigate} />
            ))}
          </ul>
        )}
      </Section>

      <Section title="Required training" intro="Courses your post requires, and when each is due.">
        <Said error={required.error} />
        {required.data && required.data.length === 0 && <p className="muted">Nothing is required of you at the moment.</p>}
        {required.data && required.data.length > 0 && (
          <ul className="rows flush" aria-label="Required training">
            {required.data.map((row) => (
              <li key={row.id}>
                <div className="row-head">
                  <a
                    className="strong"
                    href={`#/learning/${row.site}`}
                    onClick={(e) => {
                      e.preventDefault();
                      onNavigate(`/learning/${row.site}`);
                    }}
                  >
                    {row.site_title}
                  </a>
                  <span className={`chip chip-${row.state}`}>{TRAINING_STATE[row.state]}</span>
                </div>
                <span className="small muted">
                  {row.completed_on ? `Completed ${dmy(row.completed_on)}` : `Due by ${dmy(row.due_on)}`} · assigned {dmy(row.assigned_on)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="My requests to join">
        <Said error={requests.error} />
        <Said done={action.done} error={action.error} />
        {asked !== null && asked.length === 0 && <p className="muted">You have not asked to join a course.</p>}
        {asked !== null && asked.length > 0 && (
          <ul className="rows flush" aria-label="My requests to join">
            {asked.map((request) => (
              <li key={request.id}>
                <div className="row-head">
                  <span className="strong">{request.site_title}</span>
                  <span className={`chip chip-${request.state}`}>{REQUEST_STATE[request.state]}</span>
                </div>
                <span className="small muted">
                  Asked {dmyTime(request.created_at)}
                  {request.approver_name ? ` · decided by ${request.approver_name}` : " · decided by the course administrators"}
                </span>
                {request.decision_comment && <p className="small-gap">{request.decision_comment}</p>}
                {request.allowed_actions.includes("withdraw") && (
                  <div className="row-actions">
                    <button
                      type="button"
                      className="secondary"
                      disabled={action.busy}
                      aria-label={`Withdraw the request to join ${request.site_title}`}
                      onClick={() => withdraw(request)}
                    >
                      Withdraw
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}

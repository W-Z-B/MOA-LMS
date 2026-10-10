import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import { attempt } from "../../test/quizzes";
import { TeacherAttempt } from "./TeacherAttempt";

function open(routes: Parameters<typeof fakeServer>[0], start = attempt()) {
  const server = fakeServer({ "GET /quiz-attempts/30/": { body: start }, ...routes });
  render(<TeacherAttempt attemptId={30} onBack={vi.fn()} />);
  return server;
}

describe("the integrity log, for teaching staff only (item 3.25)", () => {
  it("shows the timeline, descriptively, for a secure exam attempt", async () => {
    open(
      {
        "GET /quiz-attempts/30/integrity-log/": {
          body: [
            { kind: "focus_lost", label: "Left the quiz window or tab", at: "2026-10-05T14:02:00Z" },
            { kind: "focus_resumed", label: "Returned to the quiz window or tab", at: "2026-10-05T14:02:20Z" },
          ],
        },
      },
      attempt({ is_secure_exam: true }),
    );
    expect(await screen.findByRole("heading", { name: "Integrity log" })).toBeInTheDocument();
    expect(screen.getByText(/not a verdict/)).toBeInTheDocument();
    expect(await screen.findByText(/Left the quiz window or tab/)).toBeInTheDocument();
    expect(screen.getByText(/Returned to the quiz window or tab/)).toBeInTheDocument();
  });

  it("says when nothing was reported", async () => {
    open({ "GET /quiz-attempts/30/integrity-log/": { body: [] } }, attempt({ is_secure_exam: true }));
    expect(await screen.findByText("Nothing was reported during this sitting.")).toBeInTheDocument();
  });

  it("is not shown at all for an ordinary quiz", async () => {
    open({}, attempt({ is_secure_exam: false }));
    await screen.findByRole("heading", { name: /Soils check/ });
    expect(screen.queryByRole("heading", { name: "Integrity log" })).not.toBeInTheDocument();
  });
});

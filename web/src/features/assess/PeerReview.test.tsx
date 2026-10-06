import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PeerStaffView, PeerStudentView, PeerWork } from "../../api/types-assess";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import { assignment, rubric } from "../../test/marking";
import PeerReviewScreen from "./PeerReviewScreen";
import ReviewWorkScreen from "./ReviewWorkScreen";

const setup = {
  reviews_each: 2,
  reviews_due_at: "2026-10-12T14:00:00Z",
  self_assessment: true,
  peer_weight: "20.00",
  allocated_at: "2026-10-02T14:00:00Z",
  released_at: null,
};

const staffView: PeerStaffView = {
  setup,
  rubric: true,
  work: [
    {
      submission: 21,
      label: "S2026911",
      peer_mark: "15.00",
      override: null,
      self_mark: "18.00",
      staff_mark: null,
      mark: "16.00",
      reviews: [
        { id: 70, reviewer: "S2026912", is_self: false, submitted_at: "2026-10-03T10:00:00Z", mark: "15.00", scores: [], comment: "Clear method.", moderation: "counts", moderation_note: "" },
        { id: 71, reviewer: "S2026911", is_self: true, submitted_at: "2026-10-03T11:00:00Z", mark: "18.00", scores: [], comment: "", moderation: "counts", moderation_note: "" },
      ],
    },
  ],
};

function frame(children: React.ReactNode) {
  return <FrameContext.Provider value={{ setCrumb: vi.fn(), decided: vi.fn() }}>{children}</FrameContext.Provider>;
}

describe("peer review for teaching staff (item 4.13)", () => {
  it("asks for a rubric first, then sets peer review up", async () => {
    const { calls } = fakeServer({
      "GET /assignments/3/": { body: assignment() },
      "GET /assignments/3/peer-review/": [{ body: { setup: null, rubric: false, work: [] } }],
    });
    render(frame(<PeerReviewScreen siteId={9} assignmentId={3} />));
    expect(await screen.findByText(/Peer review needs a rubric on the assignment/)).toBeInTheDocument();
    expect(calls.map((c) => c.path)).toContain("/assignments/3/peer-review/");
  });

  it("sets up, gives out, moderates, overrides, releases and folds peer marks in", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(window, "prompt").mockReturnValue("Unkind words");
    const { calls } = fakeServer({
      "GET /assignments/3/": { body: assignment() },
      "GET /assignments/3/peer-review/": [{ body: { setup: null, rubric: true, work: [] } }, { body: staffView }],
      "PUT /assignments/3/peer-review/": { body: staffView },
      "POST /assignments/3/peer-review/release/": { body: { students: 2 } },
      "POST /assignments/3/peer-review/apply/": { body: { applied: 1, skipped: 1 } },
      "POST /peer-reviews/70/moderate/": { body: { ...staffView.work[0].reviews[0], moderation: "left_out" } },
      "POST /submissions/21/peer-mark/": { body: staffView.work[0] },
    });
    const user = userEvent.setup();
    render(frame(<PeerReviewScreen siteId={9} assignmentId={3} />));
    const form = await screen.findByRole("form", { name: "Peer review settings" });
    await user.clear(within(form).getByLabelText("Pieces of work each student reviews"));
    await user.type(within(form).getByLabelText("Pieces of work each student reviews"), "2");
    await user.click(within(form).getByLabelText("Each student also assesses their own work"));
    await user.click(within(form).getByRole("button", { name: "Set up peer review" }));
    expect(await screen.findByText("Peer review is set up.")).toBeInTheDocument();
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.body).toMatchObject({ reviews_each: 2, self_assessment: true, peer_weight: "0" });

    await user.click(screen.getByText(/S2026911: peer mark 15, own 18/));
    expect(screen.getByText("Clear method.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Leave out" }));
    expect(calls.find((c) => c.path === "/peer-reviews/70/moderate/")!.body).toEqual({ moderation: "left_out", note: "Unkind words" });
    await user.type(await screen.findByLabelText(/Set the peer mark yourself/), "12");
    await user.click(screen.getByRole("button", { name: "Save peer mark" }));
    expect(calls.find((c) => c.path === "/submissions/21/peer-mark/")!.body).toEqual({ override: "12", note: "" });

    await user.click(screen.getByRole("button", { name: "Show students their reviews" }));
    expect(await screen.findByText("Reviews shown to 2 students.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Fold peer marks into the marks" }));
    expect(confirm).toHaveBeenLastCalledWith("Make each draft mark 80% your mark and 20% the peer mark?");
    expect(await screen.findByText("Peer marks folded into 1 draft mark; 1 left as they were.")).toBeInTheDocument();
  });
});

describe("peer review for students (item 4.13)", () => {
  it("lists the work to review without names, and the reviews received once released", async () => {
    const view: PeerStudentView = {
      setup: { ...setup, released_at: "2026-10-13T10:00:00Z" },
      to_do: [
        { id: 70, label: "Work 1", is_self: false, submitted_at: "2026-10-03T10:00:00Z", mark: "15.00" },
        { id: 71, label: "Your own work", is_self: true, submitted_at: null, mark: null },
      ],
      received: [{ label: "Reviewer 1", is_self: false, mark: "14.00", scores: [{ criterion: 11, level: 112, points: "5.00", comment: "Name the horizons." }], comment: "Good start." }],
    };
    fakeServer({ "GET /assignments/3/": { body: assignment() }, "GET /assignments/3/peer-review/": { body: view } });
    render(frame(<PeerReviewScreen siteId={9} assignmentId={3} />));
    expect(await screen.findByRole("link", { name: "Work 1" })).toHaveAttribute("href", "#/sites/9/peer-reviews/70");
    expect(screen.getByText("Review sent")).toBeInTheDocument();
    expect(screen.getByText("To review")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Reviewer 1: 14" })).toBeInTheDocument();
    expect(screen.getByText("Name the horizons.")).toBeInTheDocument();
  });

  it("says when the work has not been given out yet", async () => {
    fakeServer({
      "GET /assignments/3/": { body: assignment() },
      "GET /assignments/3/peer-review/": { body: { setup: { ...setup, allocated_at: null }, to_do: [], received: null } },
    });
    render(frame(<PeerReviewScreen siteId={9} assignmentId={3} />));
    expect(await screen.findByText("The work is given out after the due date. You will be told when.")).toBeInTheDocument();
    expect(screen.getByText("Your lecturer shows you the reviews once they have read them.")).toBeInTheDocument();
  });

  it("reviews one piece of work against the rubric, with a comment", async () => {
    const work: PeerWork = {
      id: 70,
      label: "Work 1",
      is_self: false,
      assignment: "Soil profile report",
      max_mark: "20.00",
      reviews_due_at: "2026-10-12T14:00:00Z",
      open: true,
      text: "The A horizon is dark.",
      files: [{ id: 5, filename: "work-1-1.pdf", download_url: "/api/v1/peer-reviews/70/files/5/" }],
      rubric,
      scores: [],
      mark: null,
      comment: "",
      submitted_at: null,
    };
    const { calls } = fakeServer({
      "GET /peer-reviews/70/": { body: work },
      "POST /peer-reviews/70/": { body: { ...work, mark: "15.00", submitted_at: "2026-10-04T10:00:00Z" } },
    });
    const user = userEvent.setup();
    render(frame(<ReviewWorkScreen siteId={9} reviewId={70} />));
    expect(await screen.findByText("The A horizon is dark.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download work-1-1.pdf" })).toHaveAttribute("href", "/api/v1/peer-reviews/70/files/5/");
    const send = screen.getByRole("button", { name: "Send review" });
    expect(send).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: /Every horizon described/ }));
    await user.click(screen.getByRole("radio", { name: /Some reasoning/ }));
    await user.type(screen.getByLabelText("Comment for the student"), "Clear.");
    await user.click(send);
    expect(await screen.findByText("Review sent: 15 out of 20.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({ comment: "Clear." });
  });

  it("shows a closed review as it was sent", async () => {
    fakeServer({
      "GET /peer-reviews/70/": {
        body: { id: 70, label: "Your own work", is_self: true, assignment: "Report", max_mark: "20.00", reviews_due_at: "2026-10-01T14:00:00Z", open: false, text: "", files: [], rubric, scores: [], mark: null, comment: "", submitted_at: null },
      },
    });
    render(frame(<ReviewWorkScreen siteId={9} reviewId={70} />));
    expect(await screen.findByText(/this one can no longer change/)).toBeInTheDocument();
    expect(screen.getByText("Nothing was handed in.")).toBeInTheDocument();
  });

  it("says when the work cannot be opened", async () => {
    fakeServer({ "GET /peer-reviews/70/": { status: 404, body: { code: "not_found", detail: "Not found." } } });
    render(frame(<ReviewWorkScreen siteId={9} reviewId={70} />));
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AssignmentDetail, WorkSubmission } from "../../api/types-marking";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import { assignment, released, submission } from "../../test/marking";
import { MarkingScreen } from "./MarkingScreen";

const andre = submission({ id: 22, student_no: "S2026912", student_name: "Andre Fung", receipt: "GSA-ZZZZZ-YYYYY" });
const history = {
  submission: 21,
  attempts: [
    {
      number: 1,
      submitted_at: "2026-10-02T14:00:00Z",
      client_submitted_at: null,
      submitted_by: "S2026911",
      is_late: true,
      receipt: "GSA-ABCDE-FGHJK",
      content_hash: "f".repeat(64),
      integrity_accepted: true,
      text: "",
      files: [],
      is_marked_attempt: true,
    },
  ],
  marks: [
    { mark: "12.00", feedback: "", is_released: false, source: "manual", rubric_scores: [], changed_by: "Marlon Bacchus", changed_at: "2026-10-03T10:00:00Z" },
  ],
  moderation: null,
};

function open(options: { a?: AssignmentDetail; rows?: WorkSubmission[]; id?: number | null; routes?: Record<string, unknown> } = {}) {
  const rows = options.rows ?? [submission(), andre];
  const server = fakeServer({
    "GET /assignments/3/": { body: options.a ?? assignment() },
    "GET /assignments/3/submissions/": { body: rows },
    "GET /submissions/21/neighbours/": { body: { position: 1, total: 2, previous: null, next: 22, previous_unmarked: null, next_unmarked: 22 } },
    "GET /submissions/21/history/": { body: history },
    ...(options.routes as Record<string, { body?: unknown }>),
  });
  const onNavigate = vi.fn();
  const setCrumb = vi.fn();
  render(
    <FrameContext.Provider value={{ setCrumb, decided: vi.fn() }}>
      <MarkingScreen siteId={9} assignmentId={3} submissionId={options.id === undefined ? 21 : options.id} onNavigate={onNavigate} />
    </FrameContext.Provider>,
  );
  return { ...server, onNavigate, setCrumb };
}

describe("the marking screen (items 2.23 to 2.25, 3.09, 3.16 to 3.18)", () => {
  it("opens on the first submission not yet marked, so its address names it", async () => {
    const marked = submission({ mark: { ...released, is_released: false } });
    const { onNavigate } = open({ id: null, rows: [marked, andre] });
    await screen.findByRole("heading", { name: "Soil profile report", level: 1 });
    // The address is set by an effect after the screen is drawn: on a busy run it can come a moment later.
    await vi.waitFor(() => expect(onNavigate).toHaveBeenCalledWith("/sites/9/assignments/3/marking/22"));
  });

  it("shows the PDF beside the mark and fills the mark from the rubric, then releases it", async () => {
    const { calls, setCrumb } = open({ routes: { "POST /submissions/21/rubric-mark/": { body: submission({ mark: released }) } } });
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "Ria Ramdial (S2026911)" })).toBeInTheDocument();
    await vi.waitFor(() => expect(setCrumb).toHaveBeenCalledWith("Marking: Soil profile report"));
    const work = screen.getByRole("region", { name: "Work handed in by Ria Ramdial (S2026911)" });
    expect(work.querySelector("object")).toHaveAttribute("data", "/api/v1/submission-files/31/download/?inline=1");
    expect(within(work).getAllByRole("link", { name: "Download S2026911-profile.pdf" })[0]).toHaveAttribute("href", "/api/v1/submission-files/31/download/");
    expect(screen.getByText("Late")).toBeInTheDocument();
    expect(await screen.findByText("1 of 2")).toBeInTheDocument();

    expect(screen.getByText("Score every criterion to fill the mark.")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Every horizon described/ }));
    await user.click(screen.getByRole("radio", { name: /Some reasoning/ }));
    expect(screen.getByText("The rubric fills the mark: 15 out of 20.")).toBeInTheDocument();
    expect(screen.getByText(/5% of the maximum \(1\) is taken, so it counts as 14/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Comment on Interpretation (optional)"), "Drainage?");
    await user.type(screen.getByLabelText("Feedback"), "Clear horizons.");
    await user.click(screen.getByRole("button", { name: "Save and release" }));

    expect(await screen.findByText("Released to Ria Ramdial.")).toBeInTheDocument();
    const sent = calls.find((c) => c.path === "/submissions/21/rubric-mark/")!;
    expect(sent.body).toEqual({
      scores: [
        { criterion: 11, level: 113, points: "10.00", comment: "" },
        { criterion: 12, level: 122, points: "5.00", comment: "Drainage?" },
      ],
      feedback: "Clear horizons.",
      is_released: true,
    });
    // The history is kept for appeals.
    await user.click(screen.getByText("History: every hand-in and every version of the mark"));
    expect(screen.getByText(/Mark 12 \(draft, manual\) by Marlon Bacchus/)).toBeInTheDocument();
  }, 20_000);

  it("keeps a typed mark and its feedback as a draft, and moves to the next not marked", async () => {
    const plain = assignment({ rubric: null, rubric_detail: null, late_penalty: "none" });
    const { calls, onNavigate } = open({ a: plain, routes: { "POST /submissions/21/mark/": { body: submission({ mark: { ...released, is_released: false, rubric_scores: [] } }) } } });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Mark out of 20"), "15");
    await user.type(screen.getByLabelText("Feedback"), "Draft thoughts");
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("Saved as a draft. The student does not see it yet.")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/submissions/21/mark/")!.body).toEqual({ mark: "15", feedback: "Draft thoughts", is_released: false });
    await user.click(await screen.findByRole("button", { name: "Next not marked" }));
    expect(onNavigate).toHaveBeenCalledWith("/sites/9/assignments/3/marking/22");
    await user.selectOptions(screen.getByRole("combobox", { name: "Student" }), "22");
    expect(onNavigate).toHaveBeenLastCalledWith("/sites/9/assignments/3/marking/22");
  });

  it("hides names while marking is anonymous", async () => {
    const hidden = [submission({ student_no: "Candidate 412345", student_name: "" })];
    open({ a: assignment({ anonymous: true }), rows: hidden });
    expect(await screen.findByText(/Anonymous marking: names are hidden/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Candidate 412345" })).toBeInTheDocument();
    expect(screen.queryByText(/Ria/)).not.toBeInTheDocument();
  });

  it("shows the SRMS lock and offers no change", async () => {
    open({ rows: [submission({ srms_locked_at: "2026-10-03T12:00:00Z", mark: released })] });
    expect(await screen.findByRole("note")).toHaveTextContent("Locked: the coursework was sent to the SRMS on 03/10/2026");
    expect(screen.queryByRole("button", { name: /Save/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Return a file or a recording")).not.toBeInTheDocument();
  });

  it("releases every mark at once, after asking", async () => {
    const rows = [submission({ mark: { ...released, is_released: false } }), andre];
    const { calls } = open({ rows, routes: { "POST /assignments/3/release/": { body: { released: 1 } } } });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    await user.click(await screen.findByText("The whole class: release, download, marks from a spreadsheet"));
    expect(screen.getByRole("link", { name: "Download every hand-in (zip)" })).toHaveAttribute("href", "/api/v1/assignments/3/download-all/");
    await user.click(screen.getByRole("button", { name: "Release all marks" }));
    expect(confirm).toHaveBeenCalled();
    expect(await screen.findByText("Released 1 mark.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/assignments/3/release/")).toBe(true);
  });

  it("shows a photograph inline and offers anything else to download", async () => {
    const photo = submission({
      text: "My notes",
      files: [
        { id: 41, filename: "pit.jpg", size: 10, sha256: "a", download_url: "/api/v1/submission-files/41/download/" },
        { id: 42, filename: "data.xlsx", size: 10, sha256: "b", download_url: "/api/v1/submission-files/42/download/" },
      ],
    });
    open({ rows: [photo] });
    const user = userEvent.setup();
    expect(await screen.findByRole("img", { name: "pit.jpg, as handed in" })).toHaveAttribute("src", "/api/v1/submission-files/41/download/?inline=1");
    expect(screen.getByText("My notes")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "data.xlsx" }));
    expect(screen.getByText("A XLSX file cannot be shown in the page.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download data.xlsx" })).toBeInTheDocument();
  });

  it("returns a feedback file and takes one back", async () => {
    const withFile = submission({
      feedback_files: [{ id: 51, filename: "comments.mp3", kind: "mp3", is_audio: true, size: 900, download_url: "/api/v1/feedback-files/51/" }],
    });
    const { calls } = open({
      rows: [submission()],
      routes: { "POST /submissions/21/feedback-files/": { status: 201, body: withFile }, "DELETE /feedback-files/51/": { status: 204 } },
    });
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Return a file or a recording"), new File(["ID3"], "comments.mp3", { type: "audio/mpeg" }));
    expect(await screen.findByLabelText("Spoken feedback comments.mp3")).toHaveAttribute("src", "/api/v1/feedback-files/51/");
    expect(calls.find((c) => c.path === "/submissions/21/feedback-files/")!.body).toBeInstanceOf(FormData);
    await user.click(screen.getByRole("button", { name: "Take back comments.mp3" }));
    await vi.waitFor(() => expect(screen.queryByLabelText("Spoken feedback comments.mp3")).not.toBeInTheDocument());
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/feedback-files/51/")).toBe(true);
  });

  it("records a second mark and then the agreed mark", async () => {
    const marked = submission({ mark: { ...released, is_released: false } });
    const second = { ...history, moderation: { first_mark: "15.00", second_mark: "13.00", second_note: "", agreed_mark: null, agreed_note: "", agreed_at: null } };
    const { calls } = open({
      a: assignment({ moderation: "double" }),
      rows: [marked],
      routes: {
        "GET /submissions/21/history/": [{ body: history }, { body: second }],
        "POST /submissions/21/second-mark/": { body: second.moderation },
        "POST /submissions/21/agree/": { body: submission({ mark: { ...released, mark: "14.00", source: "agreed", is_released: false } }) },
      },
    });
    const user = userEvent.setup();
    const panel = await screen.findByRole("region", { name: "Second marking" });
    await user.type(within(panel).getByLabelText(/Your second mark/), "13");
    await user.click(within(panel).getByRole("button", { name: "Save the second mark" }));
    expect(await within(panel).findByText("13")).toBeInTheDocument();
    await user.type(within(panel).getByLabelText("The agreed mark"), "14");
    await user.click(within(panel).getByRole("button", { name: "Record the agreed mark" }));
    expect(await screen.findByText("The agreed mark is now the mark.")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/submissions/21/agree/")!.body).toEqual({ mark: "14", note: "" });
  });

  it("marks a group's work once for every member, with an adjustment", async () => {
    const group = [submission({ group: "Team A" }), submission({ id: 22, student_no: "S2026912", student_name: "Andre Fung", group: "Team A" })];
    const { calls } = open({
      a: assignment({ is_group: true, rubric: null, rubric_detail: null }),
      rows: group,
      routes: { "GET /sites/9/my-groups/": { body: [{ id: 6, name: "Team A" }] }, "POST /assignments/3/group-mark/": { body: [] } },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByText("Mark the whole group: Team A"));
    await user.type(screen.getByLabelText("The group's mark"), "16");
    await user.type(screen.getByLabelText("Adjustment for Andre Fung (+ or −)"), "-2");
    await user.click(screen.getByRole("button", { name: "Save for every member, as a draft" }));
    await vi.waitFor(() => expect(calls.some((c) => c.path === "/assignments/3/group-mark/")).toBe(true));
    expect(calls.find((c) => c.path === "/assignments/3/group-mark/")!.body).toEqual({
      group: 6,
      mark: "16",
      feedback: "",
      is_released: false,
      adjustments: [{ student_no: "S2026912", adjustment: "-2" }],
    });
  });

  it("says when nothing has been handed in, and when the marking cannot be opened", async () => {
    open({ id: null, rows: [] });
    expect(await screen.findByText("Nothing has been handed in yet.")).toBeInTheDocument();
  });
});

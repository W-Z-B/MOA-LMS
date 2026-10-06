import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import { SpreadsheetMarks } from "./SpreadsheetMarks";

const refused = {
  applied: false,
  token: "t1",
  refused: 1,
  to_save: 1,
  rows: [
    { line: 2, student_no: "S2026911", mark: "8", feedback: "", outcome: "new", detail: "Will be saved as a draft." },
    { line: 3, student_no: "S2026999", mark: "7", feedback: "", outcome: "unknown_student", detail: "No student of this course has this number." },
  ],
};
const clean = { ...refused, token: "t2", refused: 0, rows: [refused.rows[0]] };

describe("marks from a spreadsheet, checked before they are saved (item 2.25)", () => {
  it("shows every line's outcome, refuses to apply while a line is refused, then applies the checked file", async () => {
    const { calls } = fakeServer({
      "POST /assignments/3/marks-upload/": [{ body: refused }, { body: clean }, { body: { ...clean, applied: true } }],
    });
    const onApplied = vi.fn();
    render(<SpreadsheetMarks assignmentId={3} anonymous={false} onApplied={onApplied} />);
    const user = userEvent.setup();
    expect(screen.getByText(/student number, mark and feedback/)).toBeInTheDocument();

    await user.upload(screen.getByLabelText("Spreadsheet (CSV)"), new File(["student number,mark\nS2026911,8\nS2026999,7\n"], "marks.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: "Check the file" }));
    expect(await screen.findByText("1 line is refused. Correct the file and check it again.")).toBeInTheDocument();
    const lines = within(screen.getByRole("region", { name: "Each line of the file" })).getAllByRole("row");
    expect(lines[2]).toHaveTextContent("Refused: unknown student");
    expect(lines[2]).toHaveTextContent("No student of this course has this number.");
    expect(screen.queryByRole("button", { name: /^Apply/ })).not.toBeInTheDocument();

    await user.upload(screen.getByLabelText("Spreadsheet (CSV)"), new File(["student number,mark\nS2026911,8\n"], "marks.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: "Check the file" }));
    expect(await screen.findByText("Checked: 1 mark to save, nothing refused.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Apply 1 mark" }));
    expect(await screen.findByText("Saved 1 mark as drafts.")).toBeInTheDocument();
    expect(onApplied).toHaveBeenCalled();
    const applied = calls[2].body as FormData;
    expect(applied.get("apply")).toBe("true");
    expect(applied.get("token")).toBe("t2");
    expect((calls[0].body as FormData).get("apply")).toBeNull();
  });

  it("names the pseudonym column while marking is anonymous, and says when the file cannot be read", async () => {
    fakeServer({ "POST /assignments/3/marks-upload/": { status: 400, body: { file: ["The first line must name the columns."] } } });
    render(<SpreadsheetMarks assignmentId={3} anonymous onApplied={vi.fn()} />);
    const user = userEvent.setup();
    expect(screen.getByText(/candidate \(the pseudonym\)/)).toBeInTheDocument();
    await user.upload(screen.getByLabelText("Spreadsheet (CSV)"), new File(["x"], "marks.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: "Check the file" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("file: The first line must name the columns.");
  });
});

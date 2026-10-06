import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { QType, Question, QuestionData } from "../../api/types-quizzes";
import { fakeServer } from "../../test/fetch";
import { bank, page, question } from "../../test/quizzes";
import { BanksScreen } from "./BanksScreen";
import { QuestionEditor } from "./QuestionEditor";
import { ZoneEditor } from "./ZoneEditor";

const cats = [
  { id: 3, bank: 1, parent: null, name: "Soils", position: 1 },
  { id: 4, bank: 1, parent: 3, name: "Clay", position: 1 },
];

function openBanks(routes: Parameters<typeof fakeServer>[0] = {}) {
  const server = fakeServer({
    "GET /question-banks/": { body: page([bank(), bank({ id: 2, site: null, department_code: "CROPS", name: "Crops department", owner_label: "Department CROPS", can_manage: false })]) },
    "GET /question-categories/": { body: page(cats) },
    "GET /questions/": { body: page([question()]) },
    ...routes,
  });
  render(<BanksScreen siteId={9} onBack={vi.fn()} />);
  return server;
}

describe("question banks (item 3.01)", () => {
  it("shows the course's bank with its questions, filters them and archives one", async () => {
    const { calls } = openBanks({ "PATCH /questions/5/": { body: {} } });
    expect(await screen.findByText("Plant nutrients")).toBeInTheDocument();
    expect(screen.getByText(/Multiple choice · Soils · version 1 · soils/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Category"), "4");
    await userEvent.type(screen.getByLabelText("Tag"), "clay");
    await userEvent.click(screen.getByLabelText("Archived too"));
    await waitFor(() => expect(calls.some((c) => c.path.includes("category=4") && c.path.includes("tag=clay") && c.path.includes("archived=1"))).toBe(true));
    await userEvent.click(screen.getByRole("button", { name: "Archive “Plant nutrients”" }));
    expect(await screen.findByRole("status")).toHaveTextContent("“Plant nutrients” is archived.");
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ is_archived: true });
  });

  it("refuses to delete a question in use, as the server says", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    openBanks({ "DELETE /questions/5/": { status: 409, body: { code: "in_use", detail: "A quiz or an attempt uses this question. Archive it instead." } } });
    await userEvent.click(await screen.findByRole("button", { name: "Delete “Plant nutrients”" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Archive it instead.");
  });

  it("lets a department's bank be used but not changed", async () => {
    openBanks();
    await screen.findByText("Plant nutrients");
    await userEvent.selectOptions(screen.getByLabelText("Bank"), "2");
    expect(await screen.findByText(/Your department shares this bank/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New question" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Change “/ })).not.toBeInTheDocument();
  });

  it("makes a bank for the course or a department", async () => {
    const { calls } = openBanks({ "POST /question-banks/": [{ status: 400, body: { non_field_errors: ["A bank belongs to a course site or to a department, not both."] } }, { status: 201, body: bank({ id: 7 }) }] });
    await userEvent.click(await screen.findByRole("button", { name: "New bank" }));
    await userEvent.type(screen.getByLabelText("Name"), "Livestock");
    await userEvent.selectOptions(screen.getByLabelText("Belongs to"), "department");
    await userEvent.type(screen.getByLabelText("Department code"), "liv");
    await userEvent.click(screen.getByRole("button", { name: "Make the bank" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A bank belongs to a course site or to a department");
    await userEvent.click(screen.getByRole("button", { name: "Make the bank" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(2));
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ name: "Livestock", department_code: "LIV" });
  });

  it("adds, renames and deletes categories", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { calls } = openBanks({ "POST /question-categories/": { status: 201, body: {} }, "PATCH /question-categories/4/": { body: {} }, "DELETE /question-categories/3/": { status: 204 } });
    await userEvent.click(await screen.findByRole("button", { name: "Categories" }));
    const panel = screen.getByRole("region", { name: "Categories" });
    await userEvent.type(within(panel).getByLabelText("New category"), "Loam");
    await userEvent.selectOptions(within(panel).getByLabelText("Inside"), "3");
    await userEvent.click(within(panel).getByRole("button", { name: "Add category" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ bank: 1, name: "Loam", parent: 3 }));
    const clay = within(panel).getByLabelText("Name of category Clay");
    await userEvent.clear(clay);
    await userEvent.type(clay, "Heavy clay");
    await userEvent.tab();
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ name: "Heavy clay" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Delete category Soils" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    await userEvent.click(within(panel).getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("region", { name: "Categories" })).not.toBeInTheDocument();
  });

  it("imports pasted GIFT and reports what was imported and skipped, with the reason", async () => {
    const { calls } = openBanks({
      "POST /questions/import/": [
        { status: 400, body: { code: "unreadable", detail: "The file is not Moodle XML." } },
        {
          body: {
            imported: [{ id: 9, name: "Capital", qtype: "shortanswer", category: ["Soils"] }],
            skipped: [{ name: "Broken", reason: "One choice must be worth the full mark (fraction 1)." }],
            warnings: ["A question used an image that was not imported."],
          },
        },
      ],
    });
    await userEvent.click(await screen.findByRole("button", { name: "Import" }));
    const panel = screen.getByRole("region", { name: "Import questions" });
    expect(within(panel).getByRole("button", { name: "Import" })).toBeDisabled();
    await userEvent.selectOptions(within(panel).getByLabelText("Format"), "gift");
    await userEvent.selectOptions(within(panel).getByLabelText("Into the category"), "3");
    await userEvent.type(within(panel).getByLabelText("Or paste the text"), "::Capital:: Soil? {{=loam}");
    await userEvent.click(within(panel).getByRole("button", { name: "Import" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent("The file is not Moodle XML.");
    await userEvent.click(within(panel).getByRole("button", { name: "Import" }));
    const report = await within(panel).findByRole("status");
    expect(report).toHaveTextContent("1 imported, 1 skipped.");
    expect(report).toHaveTextContent("Broken: One choice must be worth the full mark (fraction 1).");
    expect(report).toHaveTextContent("A question used an image that was not imported.");
    expect(report).toHaveTextContent("Capital (Short answer, Soils)");
    expect(calls.find((c) => c.path === "/questions/import/")!.body).toEqual({ bank: 1, format: "gift", content: "::Capital:: Soil? {=loam}", category: 3 });
  });

  it("imports a file as a form", async () => {
    const { calls } = openBanks({ "POST /questions/import/": { body: { imported: [], skipped: [], warnings: [] } } });
    await userEvent.click(await screen.findByRole("button", { name: "Import" }));
    const panel = screen.getByRole("region", { name: "Import questions" });
    await userEvent.upload(within(panel).getByLabelText(/File \(at most 5 MB\)/), new File(["<quiz/>"], "bank.xml", { type: "text/xml" }));
    expect(within(panel).queryByLabelText("Or paste the text")).not.toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Import" }));
    expect(await within(panel).findByRole("status")).toHaveTextContent("0 imported, 0 skipped.");
    const body = calls.find((c) => c.path === "/questions/import/")!.body as FormData;
    expect(body.get("format")).toBe("moodle_xml");
    expect((body.get("file") as File).name).toBe("bank.xml");
  });

  it("exports a bank as a file to save, naming what the format cannot hold", async () => {
    URL.createObjectURL = vi.fn(() => "blob:export");
    URL.revokeObjectURL = vi.fn();
    const { calls } = openBanks({
      "GET /questions/export/": { body: { format: "gift", filename: "questions-1.gift.txt", content: "::Q:: x {}", exported: 3, skipped: [{ name: "Diagram", reason: "GIFT cannot hold diagrams." }] } },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Export" }));
    const panel = screen.getByRole("region", { name: "Export questions" });
    await userEvent.selectOptions(within(panel).getByLabelText("Format"), "gift");
    await userEvent.selectOptions(within(panel).getByLabelText("Category"), "3");
    await userEvent.click(within(panel).getByRole("button", { name: "Prepare the file" }));
    const link = await within(panel).findByRole("link", { name: "Save questions-1.gift.txt" });
    expect(link).toHaveAttribute("href", "blob:export");
    expect(link).toHaveAttribute("download", "questions-1.gift.txt");
    expect(panel).toHaveTextContent("3 questions ready.");
    expect(panel).toHaveTextContent("Diagram: GIFT cannot hold diagrams.");
    expect(calls.find((c) => c.path.startsWith("/questions/export/"))!.path).toBe("/questions/export/?bank=1&file_format=gift&category=3");
  });

  it("opens the editor for a new question of the chosen type, and saves it", async () => {
    openBanks({ "POST /questions/": { status: 201, body: question({ name: "Is clay heavy?" }) } });
    await screen.findByText("Plant nutrients");
    await userEvent.selectOptions(screen.getByLabelText("Type of the new question"), "truefalse");
    await userEvent.click(screen.getByRole("button", { name: "New question" }));
    expect(screen.getByRole("heading", { name: "New question: True or false" })).toHaveFocus();
    await userEvent.type(screen.getByLabelText(/^Name/), "Is clay heavy?");
    await userEvent.type(screen.getByLabelText("Question text"), "Clay is a heavy soil.");
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved “Is clay heavy?”.");
  });

  it("says a change to a used question made a new version", async () => {
    openBanks({ "PATCH /questions/5/": { body: question({ new_version: true, versions_count: 2 }) } });
    await userEvent.click(await screen.findByRole("button", { name: "Change “Plant nutrients”" }));
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved “Plant nutrients” as version 2: attempts already made keep the earlier version.");
  });

  it("says when there are no banks, or they cannot be loaded", async () => {
    fakeServer({ "GET /question-banks/": { body: page([]) } });
    const { unmount } = render(<BanksScreen siteId={9} onBack={vi.fn()} />);
    expect(await screen.findByText(/No question banks yet/)).toBeInTheDocument();
    unmount();
    fakeServer({ "GET /question-banks/": { status: 500, body: { detail: "Server error." } } });
    render(<BanksScreen siteId={9} onBack={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
  });
});

/** The editor on its own: what each type sends to the server. */
function edit(qtype: QType, existing: Question | null = null) {
  const server = fakeServer({ "POST /questions/": { status: 201, body: question() }, "PATCH /questions/5/": { body: question() }, "POST /questions/5/image/": { body: question() } });
  const onSaved = vi.fn();
  render(<QuestionEditor bankId={1} categories={cats} question={existing} qtype={qtype} onSaved={onSaved} onCancel={vi.fn()} />);
  return { ...server, onSaved };
}

async function fillCommon(name = "Q", text = "Question text here") {
  await userEvent.type(screen.getByLabelText(/^Name/), name);
  await userEvent.type(screen.getByLabelText("Question text"), text);
}

const sent = (calls: { method: string; body: unknown }[]) => calls.find((c) => c.method === "POST" || c.method === "PATCH")!.body as { data: QuestionData } & Record<string, unknown>;

describe("the question editor, for every type (item 3.01)", () => {
  it("multiple choice: choices with a share of the mark and feedback; several right answers allow negative shares", async () => {
    const { calls, onSaved } = edit("multichoice");
    await fillCommon("Nutrients", "Which are nutrients?");
    await userEvent.type(screen.getByLabelText("Tags, separated by commas"), "soils, week 1");
    const choice = (n: number) => within(screen.getByRole("group", { name: `Choice ${n}` }));
    await userEvent.type(choice(1).getByLabelText("Text"), "Nitrogen");
    await userEvent.type(choice(1).getByLabelText("Feedback if chosen"), "Yes");
    await userEvent.type(choice(2).getByLabelText("Text"), "Potassium");
    await userEvent.type(choice(3).getByLabelText("Text"), "Sand");
    await userEvent.click(screen.getByLabelText("Several right answers"));
    await userEvent.selectOptions(choice(1).getByLabelText("Share of the mark"), "50");
    await userEvent.selectOptions(choice(2).getByLabelText("Share of the mark"), "50");
    await userEvent.selectOptions(choice(3).getByLabelText("Share of the mark"), "-100");
    await userEvent.click(screen.getByRole("button", { name: "Add a choice" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove choice 4" }));
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const body = sent(calls);
    expect(body).toMatchObject({ bank: 1, category: 3, qtype: "multichoice", name: "Nutrients", tags: ["soils", "week 1"], text: "Which are nutrients?", default_mark: "1" });
    expect(body.data).toEqual({
      single: false,
      shuffle: true,
      choices: [
        { text: "Nitrogen", fraction: 0.5, feedback: "Yes" },
        { text: "Potassium", fraction: 0.5, feedback: "" },
        { text: "Sand", fraction: -1, feedback: "" },
      ],
    });
  });

  it("lists every problem the server finds with the settings", async () => {
    fakeServer({ "POST /questions/": { status: 400, body: { data: ["Choice 'a' needs text.", "One choice must be worth the full mark (fraction 1)."], name: ["Too long."] } } });
    render(<QuestionEditor bankId={1} categories={cats} question={null} qtype="multichoice" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.submit(screen.getByRole("button", { name: "Save question" }).closest("form")!);
    const alert = await screen.findByRole("alert");
    expect(within(alert).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Choice 'a' needs text.", "One choice must be worth the full mark (fraction 1).", "name: Too long."]);
  });

  it("true or false, with feedback for each", async () => {
    const { calls } = edit("truefalse");
    await fillCommon();
    await userEvent.click(screen.getByLabelText("False"));
    await userEvent.type(screen.getByLabelText("Feedback for “True”"), "No");
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() => expect(sent(calls).data).toEqual({ correct: false, feedback_true: "No", feedback_false: "" }));
  });

  it("matching: pairs and wrong matches", async () => {
    const { calls } = edit("matching");
    await fillCommon();
    for (const [n, prompt, answer] of [[1, "Clay", "Holds water"], [2, "Sand", "Drains"], [3, "Loam", "Mix"]] as const) {
      const pair = within(screen.getByRole("group", { name: `Pair ${n}` }));
      await userEvent.type(pair.getByLabelText("Item"), prompt);
      await userEvent.type(pair.getByLabelText("Its match"), answer);
    }
    await userEvent.type(screen.getByLabelText(/Wrong matches/), "Acid{enter}{enter}");
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() => expect(sent(calls).data.extra_answers).toEqual(["Acid"]));
    expect(sent(calls).data.pairs[2]).toEqual({ prompt: "Loam", answer: "Mix" });
  });

  it("ordering: items written in the right order, moved with buttons", async () => {
    const { calls } = edit("ordering");
    await fillCommon();
    await userEvent.type(screen.getByLabelText("Item 1"), "Water");
    await userEvent.type(screen.getByLabelText("Item 2"), "Prepare");
    await userEvent.type(screen.getByLabelText("Item 3"), "Sow");
    await userEvent.click(screen.getByRole("button", { name: "Move item 2 up" }));
    await userEvent.click(screen.getByRole("button", { name: "Move item 2 down" }));
    await userEvent.selectOptions(screen.getByLabelText("Marking"), "all_or_nothing");
    await userEvent.click(screen.getByRole("button", { name: "Add an item" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove item 4" }));
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() => expect(sent(calls).data).toEqual({ items: [{ text: "Prepare" }, { text: "Sow" }, { text: "Water" }], grading: "all_or_nothing" }));
  });

  it("short answer: accepted answers with shares, and case", async () => {
    const { calls } = edit("shortanswer");
    await fillCommon();
    await userEvent.type(screen.getByLabelText("Answer"), "chlorophyll");
    await userEvent.click(screen.getByRole("button", { name: "Add an answer" }));
    const second = within(screen.getByRole("group", { name: "Accepted answer 2" }));
    await userEvent.type(second.getByLabelText("Answer"), "chloro*");
    await userEvent.selectOptions(second.getByLabelText("Share of the mark"), "50");
    await userEvent.click(screen.getByLabelText("Capital letters must match"));
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() =>
      expect(sent(calls).data).toEqual({
        answers: [
          { text: "chlorophyll", fraction: 1, feedback: "" },
          { text: "chloro*", fraction: 0.5, feedback: "" },
        ],
        case_sensitive: true,
      }),
    );
  });

  it("numerical: a value with tolerance, and units", async () => {
    const { calls } = edit("numerical");
    await fillCommon();
    await userEvent.type(screen.getByLabelText(/Number \(\* for any number\)/), "100");
    await userEvent.clear(screen.getByLabelText("Give or take"));
    await userEvent.type(screen.getByLabelText("Give or take"), "0.5");
    await userEvent.selectOptions(screen.getByLabelText("Unit"), "required");
    await userEvent.click(screen.getByRole("button", { name: "Add a unit" }));
    await userEvent.type(screen.getByLabelText("Unit 1"), "m²");
    await userEvent.selectOptions(screen.getByLabelText(/Share taken off/), "0.5");
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() =>
      expect(sent(calls).data).toEqual({ answers: [{ value: "100", tolerance: 0.5, fraction: 1, feedback: "" }], units: [{ unit: "m²", multiplier: 1 }], unit_mode: "required", unit_penalty: 0.5 }),
    );
  });

  it("fill in the blanks: one setting for each gap written in the text", async () => {
    const { calls } = edit("cloze");
    await userEvent.type(screen.getByLabelText(/^Name/), "Gaps");
    await userEvent.type(screen.getByLabelText(/^Question text/), "Plants take in [[[[1]] and give out");
    await userEvent.click(screen.getByRole("button", { name: "Add a gap at the end of the text" }));
    expect(screen.getByLabelText(/^Question text/)).toHaveValue("Plants take in [[1]] and give out [[2]]");
    const gap1 = within(screen.getByRole("group", { name: "Gap 1" }));
    await userEvent.type(gap1.getByLabelText("Answer"), "carbon dioxide");
    const gap2 = within(screen.getByRole("group", { name: "Gap 2" }));
    await userEvent.selectOptions(gap2.getByLabelText("The student"), "numerical");
    await userEvent.type(gap2.getByLabelText(/Number/), "21");
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() => expect(Object.keys(sent(calls).data.gaps)).toEqual(["1", "2"]));
    expect(sent(calls).data.gaps["1"]).toEqual({ kind: "short", answers: [{ text: "carbon dioxide", fraction: 1, feedback: "" }], case_sensitive: false, weight: 1 });
    expect(sent(calls).data.gaps["2"].answers[0]).toMatchObject({ value: "21", tolerance: 0 });
  });

  it("essay: word limits, a starting text and notes for the marker", async () => {
    const { calls } = edit("essay");
    await fillCommon();
    await userEvent.type(screen.getByLabelText(/Fewest words/), "50");
    await userEvent.type(screen.getByLabelText(/Starting text/), "Rotation");
    await userEvent.type(screen.getByLabelText(/Notes for the marker/), "Look for pests");
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() => expect(sent(calls).data).toEqual({ min_words: 50, max_words: null, response_template: "Rotation", grader_info: "Look for pests" }));
  });

  it("file response: the file types and size accepted", async () => {
    const { calls } = edit("file");
    await fillCommon();
    await userEvent.click(screen.getByLabelText("DOCX"));
    await userEvent.click(screen.getByLabelText("HEIC"));
    await userEvent.clear(screen.getByLabelText(/Largest file/));
    await userEvent.type(screen.getByLabelText(/Largest file/), "5");
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() => expect(sent(calls).data).toMatchObject({ allowed_extensions: ["pdf", "jpg", "jpeg", "png", "heic"], max_size_mb: 5 }));
  });

  it("label a diagram: labels, zones typed in, and the image sent after the question", async () => {
    URL.createObjectURL = vi.fn(() => "blob:plant");
    URL.revokeObjectURL = vi.fn();
    const { calls, onSaved } = edit("image_label");
    await fillCommon();
    await userEvent.type(screen.getByLabelText("Label 1"), "Stem");
    await userEvent.click(screen.getByRole("button", { name: "Add a label" }));
    await userEvent.type(screen.getByLabelText("Label 2"), "Soil");
    await userEvent.selectOptions(screen.getByLabelText("How students answer"), "markers");
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose the image the labels go on.");
    await userEvent.upload(screen.getByLabelText(/The image/), new File(["png"], "plant.png", { type: "image/png" }));
    const img = document.querySelector('img[src="blob:plant"][hidden]') as HTMLImageElement;
    Object.defineProperty(img, "naturalWidth", { value: 400 });
    Object.defineProperty(img, "naturalHeight", { value: 300 });
    fireEvent.load(img);
    await userEvent.click(screen.getByRole("button", { name: "Add a zone by typing its position" }));
    fireEvent.change(screen.getByLabelText("Zone 1: width"), { target: { value: "80" } });
    await userEvent.selectOptions(screen.getByLabelText("Zone 1: label"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(sent(calls).data).toEqual({
      image_width: 400,
      image_height: 300,
      mode: "markers",
      labels: [{ id: "a", text: "Stem" }, { id: "b", text: "Soil" }],
      zones: [{ label: "b", shape: "rect", x: 10, y: 10, w: 80, h: 50 }],
    });
    const upload = calls.find((c) => c.path === "/questions/5/image/")!.body as FormData;
    expect((upload.get("image") as File).name).toBe("plant.png");
  });

  it("changes a question in use, which the server keeps as a new version", async () => {
    const { calls } = edit("multichoice", question({ latest: { ...question().latest, in_use: true } }));
    expect(screen.getByRole("heading", { name: /used in an attempt: saving makes version 2/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH" && c.path === "/questions/5/")).toBe(true));
  });
});

describe("drawing zones on the image", () => {
  it("draws a rectangle from two corners and a circle from its centre and edge, in the image's pixels", () => {
    const onChange = vi.fn();
    const data = { image_width: 400, image_height: 200, labels: [{ id: "a", text: "Stem" }, { id: "b", text: "Soil" }], zones: [] };
    const { container, rerender } = render(<ZoneEditor src="/img" data={data} onChange={onChange} />);
    const svg = () => container.querySelector("svg")!;
    svg().getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 100 }) as DOMRect;
    fireEvent.click(svg(), { clientX: 10, clientY: 10 });
    expect(screen.getByText(/First point at 20, 20/)).toBeInTheDocument();
    fireEvent.click(svg(), { clientX: 60, clientY: 40 });
    expect(onChange).toHaveBeenLastCalledWith({ ...data, zones: [{ label: "a", shape: "rect", x: 20, y: 20, w: 100, h: 60 }] });

    fireEvent.change(screen.getByLabelText("Draw"), { target: { value: "circle" } });
    fireEvent.change(screen.getByLabelText("For the label"), { target: { value: "1" } });
    fireEvent.click(svg(), { clientX: 100, clientY: 50 });
    fireEvent.click(svg(), { clientX: 115, clientY: 50 });
    expect(onChange).toHaveBeenLastCalledWith({ ...data, zones: [{ label: "b", shape: "circle", x: 200, y: 100, r: 30 }] });

    // Typed instead: a polygon from points, and a zone removed.
    const zones = [{ label: "a", shape: "rect" as const, x: 1, y: 2, w: 3, h: 4 }];
    rerender(<ZoneEditor src="/img" data={{ ...data, zones }} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Zone 1: shape"), { target: { value: "polygon" } });
    expect(onChange).toHaveBeenLastCalledWith({ ...data, zones: [{ label: "a", shape: "polygon", points: [[10, 10], [60, 10], [35, 50]] }] });
    rerender(<ZoneEditor src="/img" data={{ ...data, zones: [{ label: "a", shape: "polygon", points: [[1, 1], [5, 1], [3, 4]] }] }} onChange={onChange} />);
    const points = screen.getByLabelText("Zone 1: points");
    fireEvent.change(points, { target: { value: "0,0 10,0 5,8 bad" } });
    fireEvent.blur(points);
    expect(onChange).toHaveBeenLastCalledWith({ ...data, zones: [{ label: "a", shape: "polygon", points: [[0, 0], [10, 0], [5, 8]] }] });
    fireEvent.change(screen.getByLabelText("Zone 1: shape"), { target: { value: "circle" } });
    expect(onChange).toHaveBeenLastCalledWith({ ...data, zones: [{ label: "a", shape: "circle", x: 10, y: 10, r: 25 }] });
    fireEvent.click(screen.getByRole("button", { name: "Remove zone 1" }));
    expect(onChange).toHaveBeenLastCalledWith({ ...data, zones: [] });
  });

  it("asks for the image before drawing", () => {
    render(<ZoneEditor src={null} data={{ image_width: 0, image_height: 0, labels: [], zones: [] }} onChange={vi.fn()} />);
    expect(screen.getByText("Choose the image first; then draw the zones on it.")).toBeInTheDocument();
  });
});

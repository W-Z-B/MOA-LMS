import { render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ContentItem, Module } from "../../api/types";
import type { AiStatus, DraftQuestion } from "../../api/types-connect";
import { fakeServer } from "../../test/fetch";
import { useAltSuggestions } from "./altText";
import { AiTab } from "./AiTab";
import { showsAiTab, useAiStatus } from "./status";

const item = (over: Partial<ContentItem>): ContentItem => ({
  id: 1,
  module: 7,
  kind: "page",
  title: "Soil texture",
  body: "",
  filename: null,
  download_url: null,
  url: "",
  is_published: true,
  conditions: null,
  licence: "gsa_own",
  open_licence: "",
  source: "",
  under_review: false,
  ...over,
});

const modules: Module[] = [
  {
    id: 7,
    site: 9,
    title: "Week 1: Soils",
    position: 1,
    items: [item({ id: 31 }), item({ id: 32, kind: "file", title: "Compost notes", filename: "compost.docx" }), item({ id: 33, kind: "file", title: "Scan", filename: "scan.pdf" })],
  },
];

const status = (over: Partial<AiStatus> = {}): AiStatus => ({
  enabled: true,
  teaching: true,
  drafts: true,
  study_helper: true,
  helper_available: true,
  helper_reason: null,
  pictures: true,
  ...over,
});

const question: DraftQuestion = {
  name: "Loam",
  qtype: "multichoice",
  text: "Which soil suits most crops?",
  data: {
    single: true,
    shuffle: true,
    choices: [
      { id: "a", text: "Loam", fraction: 1, feedback: "" },
      { id: "b", text: "Sand", fraction: 0, feedback: "" },
    ],
  },
  general_feedback: "Loam balances drainage and nutrients.",
};

const banks = { body: { count: 2, next: null, previous: null, results: [{ id: 5, name: "Soils", site: 9, department_code: "", description: "", owner_label: "AGR101", can_manage: true }, { id: 6, name: "Other course", site: 4, department_code: "", description: "", owner_label: "X", can_manage: true }] } };

describe("AI help for teaching staff (item 6.11)", () => {
  it("switches AI help on or off for the course", async () => {
    const { calls } = fakeServer({ "PATCH /sites/9/ai/": [{ body: status({ study_helper: false }) }, { status: 403, body: { code: "ai_off", detail: "AI help is not switched on for the GSA LMS." } }], "GET /question-banks/": banks });
    const onStatus = vi.fn();
    const user = userEvent.setup();
    render(<AiTab siteId={9} status={status()} modules={modules} onStatus={onStatus} />);
    await user.click(screen.getByLabelText(/Study helper for students/));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ study_helper: false });
    await waitFor(() => expect(onStatus).toHaveBeenCalledWith(status({ study_helper: false })));
    await user.click(screen.getByLabelText("Drafts for teaching staff"));
    expect(await screen.findByRole("alert")).toHaveTextContent("AI help is not switched on for the GSA LMS.");
  });

  it("drafts questions from a page or Word file, which the lecturer edits before saving to a bank", async () => {
    const { calls } = fakeServer({
      "GET /question-banks/": banks,
      "POST /sites/9/ai/drafts/questions/": { status: 201, body: { draft: 12, output: { questions: [question, { ...question, name: "Second" }] } } },
      "POST /questions/": { status: 201, body: { id: 77 } },
      "POST /ai/drafts/12/saved/": { status: 204 },
    });
    const user = userEvent.setup();
    render(<AiTab siteId={9} status={status()} modules={modules} onStatus={vi.fn()} />);
    const from = screen.getByLabelText("From");
    expect(within(from).getAllByRole("option").map((o) => o.textContent)).toEqual(["Soil texture", "Compost notes"]); // no PDF
    await user.selectOptions(from, "32");
    await user.click(screen.getByRole("button", { name: "Draft questions" }));
    expect(calls.find((c) => c.path === "/sites/9/ai/drafts/questions/")?.body).toEqual({ item: 32, count: 5 });
    expect(await screen.findByText(/Drafted with AI help. Check every question/)).toBeInTheDocument();
    const drafts = screen.getByRole("list", { name: "Drafted questions" });
    const first = within(drafts).getAllByRole("listitem")[0];
    await user.type(within(first).getByLabelText("Question"), " Choose one.");
    await user.click(within(first).getByLabelText("Choice 2 is right"));
    await user.clear(within(first).getByLabelText("Choice 2"));
    await user.type(within(first).getByLabelText("Choice 2"), "Sandy loam");
    expect(within(first).getAllByRole("option").map((o) => o.textContent)).toEqual(["Soils"]);
    await user.click(within(first).getByRole("button", { name: "Save to the bank" }));
    const saved = calls.find((c) => c.path === "/questions/")?.body as DraftQuestion & { bank: number };
    expect(saved.bank).toBe(5);
    expect(saved.text).toBe("Which soil suits most crops? Choose one.");
    expect(saved.data.choices.map((c) => [c.text, c.fraction])).toEqual([["Loam", 0], ["Sandy loam", 1]]);
    expect(calls.find((c) => c.path === "/ai/drafts/12/saved/")?.body).toEqual({ record: "question", id: 77 });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved “Loam” to the bank.");
    await user.click(within(screen.getByRole("list", { name: "Drafted questions" })).getByRole("button", { name: "Leave out" }));
    expect(screen.queryByRole("list", { name: "Drafted questions" })).not.toBeInTheDocument();
  });

  it("shows why a draft could not be made or saved", async () => {
    fakeServer({
      "GET /question-banks/": { body: { count: 0, next: null, previous: null, results: [] } },
      "POST /sites/9/ai/drafts/questions/": [
        { status: 502, body: { code: "ai_unreadable", detail: "The AI model's answer could not be read. Try again." } },
        { status: 201, body: { draft: 13, output: { questions: [question] } } },
      ],
    });
    const user = userEvent.setup();
    render(<AiTab siteId={9} status={status()} modules={modules} onStatus={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Draft questions" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be read");
    await user.click(screen.getByRole("button", { name: "Draft questions" }));
    expect(await screen.findByText(/Make a question bank for this course in Quizzes/)).toBeInTheDocument();
  });

  it("drafts a rubric's wording, edited and saved as a rubric of the course", async () => {
    const { calls } = fakeServer({
      "GET /question-banks/": banks,
      "POST /sites/9/ai/drafts/rubric/": {
        status: 201,
        body: {
          draft: 20,
          output: {
            title: "Soil report",
            kind: "scored",
            criteria: [{ title: "Sampling", description: "", levels: [{ points: "1", description: "Careful" }, { points: "0", description: "Careless" }] }],
          },
        },
      },
      "POST /rubrics/": [{ status: 400, body: { criteria: ["Give 'Sampling' at least one level."] } }, { status: 201, body: { id: 3 } }],
      "POST /ai/drafts/20/saved/": { status: 204 },
    });
    const user = userEvent.setup();
    render(<AiTab siteId={9} status={status()} modules={modules} onStatus={vi.fn()} />);
    await user.type(screen.getByLabelText("Rubric title"), "Soil report");
    await user.type(screen.getByLabelText("What the students are asked to do"), "Sample a plot");
    await user.type(screen.getByLabelText("Criteria, one on each line"), "Sampling{enter}{enter}");
    await user.selectOptions(screen.getByLabelText("Levels for each criterion"), "2");
    await user.click(screen.getByRole("button", { name: "Draft the wording" }));
    expect(calls.find((c) => c.path === "/sites/9/ai/drafts/rubric/")?.body).toEqual({ title: "Soil report", task: "Sample a plot", criteria: ["Sampling"], levels: 2 });
    const level = await screen.findByLabelText("1 points");
    await user.clear(level);
    await user.type(level, "Samples taken with care across the plot");
    await user.click(screen.getByRole("button", { name: "Save as a rubric of this course" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Give 'Sampling' at least one level.");
    await user.click(screen.getByRole("button", { name: "Save as a rubric of this course" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved the rubric “Soil report”.");
    const rubric = calls.filter((c) => c.path === "/rubrics/").at(-1)?.body as { site: number; criteria: { levels: { description: string }[] }[] };
    expect(rubric.site).toBe(9);
    expect(rubric.criteria[0].levels[0].description).toBe("Samples taken with care across the plot");
    expect(calls.find((c) => c.path === "/ai/drafts/20/saved/")?.body).toEqual({ record: "rubric", id: 3 });
  });

  it("can discard a rubric draft, and has nothing to draft from without material", async () => {
    fakeServer({
      "GET /question-banks/": banks,
      "POST /sites/9/ai/drafts/rubric/": [
        { status: 503, body: { code: "ai_unavailable", detail: "The AI model could not be reached. Try again later." } },
        { status: 201, body: { draft: 21, output: { title: "R", kind: "scored", criteria: [] } } },
      ],
    });
    const user = userEvent.setup();
    render(<AiTab siteId={9} status={status()} modules={[]} onStatus={vi.fn()} />);
    expect(screen.getByText(/Put up a page, or a Word or PowerPoint file/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Rubric title"), "R");
    await user.type(screen.getByLabelText("What the students are asked to do"), "T");
    await user.type(screen.getByLabelText("Criteria, one on each line"), "C");
    await user.click(screen.getByRole("button", { name: "Draft the wording" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be reached");
    await user.click(screen.getByRole("button", { name: "Draft the wording" }));
    await user.click(await screen.findByRole("button", { name: "Discard" }));
    expect(screen.queryByRole("button", { name: "Save as a rubric of this course" })).not.toBeInTheDocument();
  });
});

describe("the study helper (item 6.12)", () => {
  it("answers from the course's material and shows the sources", async () => {
    const { calls } = fakeServer({
      "POST /sites/9/ai/ask/": [
        { body: { answered: true, answer: "Loam [1].", sources: [{ item: 31, title: "Soil texture", module: "Week 1: Soils", link: "/sites/9/pages/31" }] } },
        { body: { answered: false, answer: "I could not find this in your course's material, so I cannot answer it.", sources: [] } },
        { status: 403, body: { code: "assessment_open", detail: "The study helper is off while the quiz “Soils test” is open to you." } },
      ],
    });
    const user = userEvent.setup();
    render(<AiTab siteId={9} status={status({ teaching: false, drafts: false })} modules={modules} onStatus={vi.fn()} />);
    expect(screen.queryByRole("heading", { name: "AI help on this course" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Your question"), "Which soil suits most crops?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(calls[0].body).toEqual({ question: "Which soil suits most crops?" });
    const answer = await screen.findByRole("status");
    expect(answer).toHaveTextContent("Loam [1].");
    expect(within(answer).getByRole("link", { name: "Soil texture" })).toHaveAttribute("href", "#/sites/9/pages/31");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(/could not find this in your course's material/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Soils test");
  });

  it("says why it is off for a student", () => {
    render(
      <AiTab
        siteId={9}
        status={status({ teaching: false, drafts: false, helper_available: false, helper_reason: "The study helper is off while you have a quiz attempt in progress on this course." })}
        modules={modules}
        onStatus={vi.fn()}
      />,
    );
    expect(screen.getByText(/quiz attempt in progress/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Your question")).not.toBeInTheDocument();
  });
});

describe("whether the AI help tab is shown", () => {
  it("is hidden while AI is off, and from a student while the helper may not be used", async () => {
    expect(showsAiTab(null)).toBe(false);
    expect(showsAiTab(status({ enabled: false }))).toBe(false);
    expect(showsAiTab(status({ teaching: false, helper_available: false }))).toBe(false);
    expect(showsAiTab(status({ teaching: false }))).toBe(true);
    expect(showsAiTab(status({ helper_available: false }))).toBe(true);
    fakeServer({ "GET /sites/9/ai/": [{ body: status() }, { status: 500, body: {} }] });
    const { result } = renderHook(() => useAiStatus(9));
    await waitFor(() => expect(result.current[0]).toEqual(status()));
    const failed = renderHook(() => useAiStatus(9));
    await waitFor(() => expect(failed.result.current[0]).toBeNull());
  });

  it("offers picture descriptions only where drafts and a picture model are on", async () => {
    const { calls } = fakeServer({
      "GET /sites/9/ai/": [{ body: status() }, { body: status({ pictures: false }) }],
      "POST /sites/9/ai/drafts/alt-text/": { status: 201, body: { draft: 30, output: { alt_text: "Maize seedlings" } } },
      "POST /ai/drafts/30/saved/": { status: 204 },
    });
    const { result } = renderHook(() => useAltSuggestions(9));
    await waitFor(() => expect(result.current).toBeDefined());
    const suggestion = await result.current!({ id: 31 });
    expect(suggestion.text).toBe("Maize seedlings");
    suggestion.used();
    await waitFor(() => expect(calls.find((c) => c.path === "/ai/drafts/30/saved/")?.body).toEqual({ record: "content", id: 31 }));
    const off = renderHook(() => useAltSuggestions(9));
    await waitFor(() => expect(calls.filter((c) => c.path === "/sites/9/ai/")).toHaveLength(2));
    expect(off.result.current).toBeUndefined();
  });
});

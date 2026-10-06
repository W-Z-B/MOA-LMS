import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AttemptQuestion } from "../../api/types-quizzes";
import { mcQuestion } from "../../test/quizzes";
import { AnswerInput } from "./AnswerInput";
import { Countdown } from "./Countdown";
import { ClozeText, Rich } from "./Rich";

/** The input as it is used: the answer given is kept and passed back in, and every change is recorded. */
function Harness({ q, initial = null, onChange, onFile = vi.fn() }: { q: AttemptQuestion; initial?: Record<string, unknown> | null; onChange: (r: unknown, typing?: boolean) => void; onFile?: (f: File) => void }) {
  const [value, setValue] = useState(initial);
  return (
    <AnswerInput
      q={q}
      value={value}
      onFile={onFile}
      onChange={(r, typing) => {
        setValue(r);
        onChange(r, typing);
      }}
    />
  );
}

const q = (over: Partial<AttemptQuestion>) => mcQuestion(over);

describe("question text is the server's cleaned HTML, placed as it is", () => {
  it("shows the formatting the allow-list keeps", () => {
    render(<Rich html="<p>Which <strong>soil</strong>?</p>" />);
    expect(screen.getByText("soil").tagName).toBe("STRONG");
  });

  it("puts an input in each gap of a fill-in-the-blanks text", () => {
    render(<ClozeText html="<p>Plants take in [[1]] and give out [[2]].</p>" gap={(key) => <input aria-label={`Gap ${key}`} />} />);
    expect(screen.getByLabelText("Gap 1").closest("p")).toHaveTextContent("Plants take in and give out .");
    expect(screen.getByLabelText("Gap 2")).toBeInTheDocument();
  });
});

describe("answering each type of question (item 3.01)", () => {
  it("multiple choice, one answer: a radio group that can be cleared", async () => {
    const onChange = vi.fn();
    render(<Harness q={q({})} onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "Nitrogen" }));
    expect(onChange).toHaveBeenLastCalledWith({ choice: "a" }, undefined);
    await userEvent.click(screen.getByRole("button", { name: "Clear my choice" }));
    expect(onChange).toHaveBeenLastCalledWith({ choice: null }, undefined);
  });

  it("multiple choice, several answers: checkboxes in the order shown", async () => {
    const onChange = vi.fn();
    render(<Harness q={q({ data: { single: false, choices: [{ id: "b", text: "Compost" }, { id: "a", text: "Humus" }] } })} onChange={onChange} />);
    await userEvent.click(screen.getByRole("checkbox", { name: "Humus" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Compost" }));
    expect(onChange).toHaveBeenLastCalledWith({ choices: ["b", "a"] }, undefined);
    await userEvent.click(screen.getByRole("checkbox", { name: "Humus" }));
    expect(onChange).toHaveBeenLastCalledWith({ choices: ["b"] }, undefined);
  });

  it("true or false", async () => {
    const onChange = vi.fn();
    render(<Harness q={q({ qtype: "truefalse", data: {} })} onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "False" }));
    expect(onChange).toHaveBeenLastCalledWith({ answer: false }, undefined);
  });

  it("matching: a list of answers beside each item", async () => {
    const onChange = vi.fn();
    render(<Harness q={q({ qtype: "matching", data: { prompts: [{ id: "a", text: "Clay" }, { id: "b", text: "Sand" }], answers: ["Drains fast", "Holds water"] } })} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Clay" }), "Holds water");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Sand" }), "Drains fast");
    expect(onChange).toHaveBeenLastCalledWith({ matches: { a: "Holds water", b: "Drains fast" } }, undefined);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Clay" }), "");
    expect(onChange).toHaveBeenLastCalledWith({ matches: { a: null, b: "Drains fast" } }, undefined);
  });

  it("ordering: up and down buttons, or keeping the order as shown", async () => {
    const onChange = vi.fn();
    render(<Harness q={q({ qtype: "ordering", data: { items: [{ id: "b", text: "Water" }, { id: "a", text: "Sow" }] } })} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "Move up: item 1" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Keep this order as my answer" }));
    expect(onChange).toHaveBeenLastCalledWith({ order: ["b", "a"] }, undefined);
    await userEvent.click(screen.getByRole("button", { name: "Move up: item 2" }));
    expect(onChange).toHaveBeenLastCalledWith({ order: ["a", "b"] }, undefined);
    await userEvent.click(screen.getByRole("button", { name: "Move down: item 1" }));
    expect(onChange).toHaveBeenLastCalledWith({ order: ["b", "a"] }, undefined);
  });

  it("short answer and essay are typed: saved after a pause, and an essay counts its words", async () => {
    const onChange = vi.fn();
    render(<Harness q={q({ qtype: "shortanswer", data: {} })} onChange={onChange} />);
    await userEvent.type(screen.getByLabelText("Your answer"), "humus");
    expect(onChange).toHaveBeenLastCalledWith({ text: "humus" }, true);
  });

  it("an essay starts from its template and counts words against the limits", async () => {
    const onChange = vi.fn();
    render(<Harness q={q({ qtype: "essay", data: { min_words: 3, max_words: 50, response_template: "Rotation" } })} onChange={onChange} />);
    expect(screen.getByLabelText(/Your answer/)).toHaveValue("Rotation");
    expect(screen.getByText(/1 word \(write at least 3 and at most 50 words\)/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Your answer/), " breaks pests");
    expect(screen.getByText(/3 words/)).toBeInTheDocument();
  });

  it("numerical: a number and, where the question has them, a unit", async () => {
    const onChange = vi.fn();
    render(<Harness q={q({ qtype: "numerical", data: { units: ["m²", "ha"], unit_mode: "optional" } })} onChange={onChange} />);
    await userEvent.type(screen.getByLabelText("Your answer (a number)"), "100");
    expect(onChange).toHaveBeenLastCalledWith({ value: "100", unit: "" }, true);
    await userEvent.selectOptions(screen.getByLabelText("Unit (optional)"), "m²");
    expect(onChange).toHaveBeenLastCalledWith({ value: "100", unit: "m²" }, undefined);
  });

  it("file response: the chosen file is handed over to be sent at once", async () => {
    const onFile = vi.fn();
    render(<Harness q={q({ qtype: "file", data: { allowed_extensions: ["pdf", "jpg"], max_size_mb: 5 } })} initial={{ filename: "old.pdf" }} onChange={vi.fn()} onFile={onFile} />);
    expect(screen.getByText("Uploaded: old.pdf")).toBeInTheDocument();
    const file = new File(["x"], "bed.jpg", { type: "image/jpeg" });
    await userEvent.upload(screen.getByLabelText(/Your file \(PDF, JPG; at most 5 MB\)/), file);
    expect(onFile).toHaveBeenCalledWith(file);
  });

  it("fill in the blanks: a field or a list in each gap of the text", async () => {
    const onChange = vi.fn();
    render(
      <Harness
        q={q({ qtype: "cloze", text: "<p>Plants take in [[1]] and give out [[2]].</p>", data: { gaps: { "1": { kind: "short" }, "2": { kind: "choice", choices: ["oxygen", "nitrogen"] } } } })}
        onChange={onChange}
      />,
    );
    await userEvent.type(screen.getByRole("textbox", { name: "Gap 1" }), "CO2");
    expect(onChange).toHaveBeenLastCalledWith({ gaps: { "1": "CO2" } }, true);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Gap 2" }), "oxygen");
    expect(onChange).toHaveBeenLastCalledWith({ gaps: { "1": "CO2", "2": "oxygen" } }, false);
  });

  const diagram = { image_width: 400, image_height: 200, labels: [{ id: "a", text: "Stem" }, { id: "b", text: "Soil" }] };

  it("label a diagram: a label chosen for each numbered zone", async () => {
    const onChange = vi.fn();
    render(<Harness q={q({ qtype: "image_label", image_url: "/img", data: { ...diagram, mode: "drop_zones", zones: [{ id: "z1", shape: "rect", x: 1, y: 1, w: 5, h: 5 }, { id: "z2", shape: "circle", x: 9, y: 9, r: 3 }, { id: "z3", shape: "polygon", points: [[0, 0], [3, 0], [0, 3]] }] } })} onChange={onChange} />);
    expect(screen.getByRole("img", { name: /3 numbered zones/ })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Zone 2" }), "Soil");
    expect(onChange).toHaveBeenLastCalledWith({ zones: { z2: "b" } }, undefined);
  });

  it("label a diagram with hidden zones: tap the image, or type where the label goes", async () => {
    const onChange = vi.fn();
    const { container } = render(<Harness q={q({ qtype: "image_label", image_url: "/img", data: { ...diagram, mode: "markers" } })} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Place “Stem”" }));
    expect(screen.getByRole("button", { name: "Tap the diagram for “Stem”" })).toHaveAttribute("aria-pressed", "true");
    const svg = container.querySelector("svg")!;
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 100 }) as DOMRect;
    fireEvent.click(svg, { clientX: 100, clientY: 50 });
    expect(onChange).toHaveBeenLastCalledWith({ placements: [{ label: "a", x: 200, y: 100 }] }, undefined);
    fireEvent.change(screen.getByLabelText("Soil: across"), { target: { value: "30" } });
    expect(onChange).toHaveBeenLastCalledWith({ placements: [{ label: "a", x: 200, y: 100 }, { label: "b", x: 30, y: 0 }] }, undefined);
    fireEvent.change(screen.getByLabelText("Stem: down"), { target: { value: "40" } });
    expect(onChange).toHaveBeenLastCalledWith({ placements: [{ label: "b", x: 30, y: 0 }, { label: "a", x: 200, y: 40 }] }, undefined);
  });
});

describe("the countdown, from the server's time left (item 3.03)", () => {
  afterEach(() => vi.useRealTimers());

  it("counts down every second, tells a screen reader at 5 and 1 minutes only, and submits at nought", () => {
    vi.useFakeTimers();
    const onExpire = vi.fn();
    render(<Countdown secondsLeft={302} syncedAt={Date.now()} onExpire={onExpire} />);
    expect(screen.getByRole("timer")).toHaveTextContent("5:02");
    act(() => vi.advanceTimersByTime(1000));
    const live = document.querySelector("[aria-live]")!;
    expect(live).toHaveTextContent("");
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByRole("timer")).toHaveTextContent("4:58");
    expect(live).toHaveTextContent("5 minutes left.");
    act(() => vi.advanceTimersByTime(60_000));
    expect(live).toHaveTextContent("5 minutes left.");
    act(() => vi.advanceTimersByTime(180_000));
    expect(live).toHaveTextContent("1 minute left.");
    expect(onExpire).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(60_000));
    expect(screen.getByRole("timer")).toHaveTextContent("0:00");
    expect(live).toHaveTextContent("Time is up.");
    act(() => vi.advanceTimersByTime(5000));
    expect(onExpire).toHaveBeenCalledTimes(1);
  });
});

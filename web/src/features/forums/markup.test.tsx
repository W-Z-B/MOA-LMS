import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Composer } from "./Composer";
import { preview, toHtml, toText } from "./markup";

describe("simple formatting for posts and messages (items 4.08, 4.11)", () => {
  it("turns bold, italic, lists and links into the few tags the server keeps, escaping everything else", () => {
    expect(toHtml("Spacing is **45 cm**, *not* 30.")).toBe("<p>Spacing is <strong>45 cm</strong>, <em>not</em> 30.</p>");
    expect(toHtml("Bring:\n- a trowel\n- *gloves*\n\nThanks")).toBe(
      "<p>Bring:</p><ul><li>a trowel</li><li><em>gloves</em></li></ul><p>Thanks</p>",
    );
    expect(toHtml("See [the guide](https://gsa.example/guide) or https://gsa.example/faq.")).toBe(
      '<p>See <a href="https://gsa.example/guide">the guide</a> or <a href="https://gsa.example/faq">https://gsa.example/faq</a>.</p>',
    );
    expect(toHtml("line one\nline two")).toBe("<p>line one<br>line two</p>");
    // Anything that looks like HTML stays text; a script never reaches the server as a tag.
    expect(toHtml('<script>alert("x")</script> & [x](javascript:alert(1))')).toBe(
      "<p>&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; [x](javascript:alert(1))</p>",
    );
    expect(toHtml("  \n\n ")).toBe("");
  });

  it("reads a cleaned post back as the same text, for a change within the edit window", () => {
    const text = "Spacing is **45 cm**, *not* 30.\n\n- a trowel\n- gloves\n\nSee [the guide](https://gsa.example/guide) or https://gsa.example/faq";
    expect(toText(toHtml(text))).toBe(text);
    expect(toText("<h2>Title</h2><blockquote>Quote</blockquote><p>a<br>b</p>")).toBe("Title\n\nQuote\n\na\nb");
    expect(preview("<p><strong>Hello</strong> there</p>")).toBe("Hello there");
    expect(preview(`<p>${"a".repeat(200)}</p>`, 10)).toBe(`${"a".repeat(9)}…`);
  });
});

function Harness() {
  const [value, setValue] = useState("Plant seeds");
  return <Composer label="Your reply" value={value} onChange={setValue} />;
}

describe("the composer", () => {
  it("writes the marks for bold, italic, a list and a link into the text", () => {
    render(<Harness />);
    const box = screen.getByLabelText("Your reply") as HTMLTextAreaElement;
    expect(box).toHaveAccessibleDescription(/\*\*bold\*\*/);
    box.setSelectionRange(0, 5);
    fireEvent.click(screen.getByRole("button", { name: "Bold" }));
    expect(box.value).toBe("**Plant** seeds");
    box.setSelectionRange(box.value.length, box.value.length);
    fireEvent.click(screen.getByRole("button", { name: "Italic" }));
    expect(box.value).toBe("**Plant** seeds*words*");
    box.setSelectionRange(0, 0);
    fireEvent.click(screen.getByRole("button", { name: "List" }));
    expect(box.value).toBe("- **Plant** seeds*words*");
    box.setSelectionRange(box.value.length, box.value.length);
    fireEvent.click(screen.getByRole("button", { name: "Link" }));
    expect(box.value).toBe("- **Plant** seeds*words*[words](https://)");
    expect(screen.getByRole("group", { name: "Formatting for your reply" })).toBeInTheDocument();
  });
});

import { useId, useRef } from "react";

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  /** Shown under the label, before the formatting help. */
  hint?: string;
  autoFocus?: boolean;
}

type Mark = "bold" | "italic" | "list" | "link";

/**
 * A plain text box with four buttons for simple formatting (items 4.08, 4.11): bold, italic, a list and a
 * link. The buttons write the marks into the text (markup.ts turns them into HTML), so the box works the
 * same with a phone's keyboard, a screen reader or no buttons at all.
 */
export function Composer({ label, value, onChange, rows = 5, hint, autoFocus }: Props) {
  const box = useRef<HTMLTextAreaElement>(null);
  const help = useId();

  function apply(mark: Mark) {
    const area = box.current;
    const start = area?.selectionStart ?? value.length;
    const end = area?.selectionEnd ?? value.length;
    const chosen = value.slice(start, end);
    let text: string;
    let caret: [number, number];
    if (mark === "list") {
      const lineStart = value.lastIndexOf("\n", start - 1) + 1;
      const lines = value.slice(lineStart, end).split("\n").map((line) => (line.startsWith("- ") ? line : `- ${line}`));
      const block = lines.join("\n");
      text = value.slice(0, lineStart) + block + value.slice(end);
      caret = [lineStart + block.length, lineStart + block.length];
    } else if (mark === "link") {
      const words = chosen || "words";
      const inserted = `[${words}](https://)`;
      text = value.slice(0, start) + inserted + value.slice(end);
      const at = start + words.length + 3;
      caret = [at + "https://".length, at + "https://".length];
    } else {
      const sign = mark === "bold" ? "**" : "*";
      const words = chosen || (mark === "bold" ? "bold words" : "words");
      text = value.slice(0, start) + sign + words + sign + value.slice(end);
      caret = [start + sign.length, start + sign.length + words.length];
    }
    onChange(text);
    requestAnimationFrame(() => {
      box.current?.focus();
      box.current?.setSelectionRange(...caret);
    });
  }

  return (
    <div className="composer">
      <label>
        {label}
        {hint && <span className="muted small composer-hint">{hint}</span>}
        <textarea
          ref={box}
          rows={rows}
          value={value}
          autoFocus={autoFocus}
          aria-describedby={help}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
      <div className="composer-tools" role="group" aria-label={`Formatting for ${label.toLowerCase()}`}>
        <button type="button" className="secondary small-button" onClick={() => apply("bold")}>
          <strong>Bold</strong>
        </button>
        <button type="button" className="secondary small-button" onClick={() => apply("italic")}>
          <em>Italic</em>
        </button>
        <button type="button" className="secondary small-button" onClick={() => apply("list")}>
          List
        </button>
        <button type="button" className="secondary small-button" onClick={() => apply("link")}>
          Link
        </button>
      </div>
      <p id={help} className="muted small composer-help">
        **bold**, *italic*, a line starting with - for a list, [words](https://address) for a link.
      </p>
    </div>
  );
}

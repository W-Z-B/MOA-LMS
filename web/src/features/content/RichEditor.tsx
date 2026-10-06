import { Editor, isNodeSelection } from "@tiptap/core";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { pageExtensions } from "./extensions";
import { drawFormula, loadKatex } from "./maths";

/** A picture that is a file on the course, which a page may show. */
export interface Picture {
  id: number;
  title: string;
  url: string;
}

interface Props {
  /** The page's text when the editor opens; later changes come from the person writing. */
  initialHtml: string;
  onChange: (html: string) => void;
  pictures: Picture[];
  label: string;
}

type Panel = "link" | "picture" | "maths" | null;

/**
 * The page editor (item 2.12): TipTap without its React layer, so the bundle carries only the core. Every
 * control is a labelled button in one toolbar, and links, pictures and maths open a small form under it
 * instead of a dialog box, so the editor works the same with a keyboard, a screen reader or on a phone.
 */
export function RichEditor({ initialHtml, onChange, pictures, label }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const changed = useRef(onChange);
  // The editor is made once: the text and name it opens with are read only then.
  const opening = useRef({ initialHtml, label });
  const [editor, setEditor] = useState<Editor | null>(null);
  const [, setVersion] = useState(0);
  const [panel, setPanel] = useState<Panel>(null);

  useEffect(() => {
    changed.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (!host.current) return;
    const made = new Editor({
      element: host.current,
      extensions: pageExtensions(),
      // TipTap would add its base styles as a style element, which the Content-Security-Policy refuses: they
      // are in content.css instead.
      injectCSS: false,
      content: opening.current.initialHtml,
      editorProps: { attributes: { "aria-label": opening.current.label, role: "textbox", "aria-multiline": "true", class: "editor-area" } },
      onUpdate: ({ editor: e }) => changed.current(e.getHTML()),
      // The toolbar shows what is on at the cursor: drawn again after every change of text or selection.
      onTransaction: () => setVersion((v) => v + 1),
    });
    setEditor(made);
    return () => made.destroy();
  }, []);

  const run = (command: (chain: ReturnType<Editor["chain"]>) => ReturnType<Editor["chain"]>) => {
    if (editor) command(editor.chain().focus()).run();
  };
  const on = (name: string, attrs?: Record<string, unknown>) => editor?.isActive(name, attrs) ?? false;
  const inTable = on("table");

  const tool = (text: string, action: () => void, pressed?: boolean, disabled = false): ReactNode => (
    <button key={text} type="button" className="tool" aria-pressed={pressed} onClick={action} disabled={!editor || disabled}>
      {text}
    </button>
  );
  const toggle = (which: Exclude<Panel, null>) => setPanel(panel === which ? null : which);

  return (
    <div className="rich-editor">
      <div className="toolbar" role="toolbar" aria-label="Formatting">
        {[2, 3, 4].map((level) =>
          tool(`Heading ${level}`, () => run((c) => c.toggleHeading({ level: level as 2 | 3 | 4 })), on("heading", { level })),
        )}
        {tool("Text", () => run((c) => c.setParagraph()), on("paragraph"))}
        {tool("Bold", () => run((c) => c.toggleBold()), on("bold"))}
        {tool("Italic", () => run((c) => c.toggleItalic()), on("italic"))}
        {tool("List", () => run((c) => c.toggleBulletList()), on("bulletList"))}
        {tool("Numbered list", () => run((c) => c.toggleOrderedList()), on("orderedList"))}
        {tool("Quote", () => run((c) => c.toggleBlockquote()), on("blockquote"))}
        {tool("Code", () => run((c) => c.toggleCode()), on("code"))}
        {tool("Code block", () => run((c) => c.toggleCodeBlock()), on("codeBlock"))}
        {tool("Link", () => toggle("link"), panel === "link" || on("link"))}
        {tool("Picture", () => toggle("picture"), panel === "picture" || on("image"))}
        {tool("Maths", () => toggle("maths"), panel === "maths" || on("mathInline") || on("mathBlock"))}
        {tool("Table", () => run((c) => c.insertTable({ rows: 3, cols: 3, withHeaderRow: true })), undefined, inTable)}
        {tool("Undo", () => run((c) => c.undo()), undefined, !editor?.can().undo())}
        {tool("Redo", () => run((c) => c.redo()), undefined, !editor?.can().redo())}
      </div>
      {inTable && (
        <div className="toolbar" role="toolbar" aria-label="Table">
          {tool("Add row", () => run((c) => c.addRowAfter()))}
          {tool("Add column", () => run((c) => c.addColumnAfter()))}
          {tool("Remove row", () => run((c) => c.deleteRow()))}
          {tool("Remove column", () => run((c) => c.deleteColumn()))}
          {tool("Remove table", () => run((c) => c.deleteTable()))}
        </div>
      )}
      {editor && panel === "link" && <LinkForm editor={editor} onDone={() => setPanel(null)} />}
      {editor && panel === "picture" && <PictureForm editor={editor} pictures={pictures} onDone={() => setPanel(null)} />}
      {editor && panel === "maths" && <MathsForm editor={editor} onDone={() => setPanel(null)} />}
      <div ref={host} className="editor-host" />
    </div>
  );
}

function LinkForm({ editor, onDone }: { editor: Editor; onDone: () => void }) {
  const [href, setHref] = useState<string>(() => String(editor.getAttributes("link").href ?? ""));
  const apply = () => {
    const address = href.trim();
    const chain = editor.chain().focus().extendMarkRange("link");
    (address ? chain.setLink({ href: address }) : chain.unsetLink()).run();
    onDone();
  };
  return (
    <div className="editor-panel" role="group" aria-label="Link">
      <label>
        Web address or e-mail
        <input type="url" inputMode="url" placeholder="https://" value={href} onChange={(e) => setHref(e.target.value)} />
      </label>
      <p className="muted small">Select the words that say where the link goes first: "planting guide", not "click here".</p>
      <div className="actions">
        <button type="button" className="secondary" onClick={onDone}>
          Cancel
        </button>
        {editor.isActive("link") && (
          <button
            type="button"
            className="secondary"
            onClick={() => {
              editor.chain().focus().extendMarkRange("link").unsetLink().run();
              onDone();
            }}
          >
            Remove link
          </button>
        )}
        <button type="button" onClick={apply} disabled={!href.trim()}>
          Apply link
        </button>
      </div>
    </div>
  );
}

function PictureForm({ editor, pictures, onDone }: { editor: Editor; pictures: Picture[]; onDone: () => void }) {
  const chosen = editor.isActive("image") ? editor.getAttributes("image") : null;
  const [src, setSrc] = useState<string>(String(chosen?.src ?? pictures[0]?.url ?? ""));
  const [alt, setAlt] = useState<string>(String(chosen?.alt ?? ""));
  if (pictures.length === 0 && !chosen)
    return (
      <div className="editor-panel" role="group" aria-label="Picture">
        <p className="notice">
          This course has no photographs yet. Put the picture up as a file on the course (JPG, PNG or WebP), then add it to the page.
        </p>
        <div className="actions">
          <button type="button" className="secondary" onClick={onDone}>
            Close
          </button>
        </div>
      </div>
    );
  const insert = () => {
    const text = alt.trim();
    if (chosen) editor.chain().focus().updateAttributes("image", { src, alt: text }).run();
    else editor.chain().focus().setImage({ src, alt: text }).run();
    onDone();
  };
  return (
    <div className="editor-panel" role="group" aria-label="Picture">
      <label>
        Picture from this course's files
        <select value={src} onChange={(e) => setSrc(e.target.value)}>
          {pictures.map((p) => (
            <option key={p.id} value={p.url}>
              {p.title}
            </option>
          ))}
        </select>
      </label>
      <label>
        What the picture shows (alternative text, required)
        <input value={alt} onChange={(e) => setAlt(e.target.value)} placeholder="Maize seedlings ten days after sowing" required aria-required="true" />
      </label>
      <p className="muted small">Read aloud to students who cannot see the picture. Say what matters in it, in a few words.</p>
      <div className="actions">
        <button type="button" className="secondary" onClick={onDone}>
          Cancel
        </button>
        <button type="button" onClick={insert} disabled={!src || !alt.trim()}>
          {chosen ? "Update picture" : "Add picture"}
        </button>
      </div>
    </div>
  );
}

function MathsForm({ editor, onDone }: { editor: Editor; onDone: () => void }) {
  const selection = editor.state.selection;
  const current = isNodeSelection(selection) && ["mathInline", "mathBlock"].includes(selection.node.type.name) ? selection.node : null;
  const [tex, setTex] = useState<string>(String(current?.attrs.tex ?? ""));
  const [displayed, setDisplayed] = useState(current?.type.name === "mathBlock");
  const preview = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = preview.current;
    if (!element) return;
    if (!tex.trim()) {
      element.textContent = "Type a formula to see it here.";
      return;
    }
    let live = true;
    loadKatex()
      .then((katex) => live && drawFormula(katex, element, tex, displayed))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [tex, displayed]);

  const insert = () => {
    editor
      .chain()
      .focus()
      .insertContent({ type: displayed ? "mathBlock" : "mathInline", attrs: { tex: tex.trim() } })
      .run();
    onDone();
  };
  return (
    <div className="editor-panel" role="group" aria-label="Maths">
      <label>
        Formula, written in TeX
        <textarea value={tex} onChange={(e) => setTex(e.target.value)} placeholder="\frac{a}{b}" spellCheck={false} rows={2} />
      </label>
      <label className="inline">
        <input type="checkbox" checked={displayed} onChange={(e) => setDisplayed(e.target.checked)} /> On a line of its own
      </label>
      <div className="maths-preview" aria-live="polite">
        <span className="muted small">Preview</span>
        <div ref={preview} />
      </div>
      <div className="actions">
        <button type="button" className="secondary" onClick={onDone}>
          Cancel
        </button>
        <button type="button" onClick={insert} disabled={!tex.trim()}>
          {current ? "Update formula" : "Add formula"}
        </button>
      </div>
    </div>
  );
}

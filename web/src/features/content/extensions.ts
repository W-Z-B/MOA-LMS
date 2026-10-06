/**
 * What the page editor can write (item 2.12, ADR 0012: TipTap), matched to what the server keeps
 * (courses.richtext): headings 2 to 4 (the page title is the level 1 heading), paragraphs, lists, quotations,
 * bold and italic, links, code, tables, pictures that are files on the course, and maths as TeX. Anything
 * the server would strip is left out of the editor, so what is written is what is saved.
 *
 * Nothing here writes a style attribute: the Content-Security-Policy forbids inline styles, so tables are
 * written without TipTap's width styles and maths is drawn through the CSS object model.
 */

import { Node, mergeAttributes, type Extensions } from "@tiptap/core";
import Image from "@tiptap/extension-image";
import { Table, TableCell, TableHeader, TableRow } from "@tiptap/extension-table";
import StarterKit from "@tiptap/starter-kit";
import { drawFormula, loadKatex } from "./maths";

/** A formula's node view: drawn by KaTeX once it has loaded, its TeX until then. */
function formulaView(displayed: boolean) {
  return ({ node }: { node: { attrs: Record<string, unknown> } }) => {
    const dom = document.createElement(displayed ? "div" : "span");
    const tex = String(node.attrs.tex ?? "");
    dom.className = displayed ? "math-node math-block" : "math-node";
    dom.setAttribute("data-math", tex);
    dom.textContent = tex;
    loadKatex()
      .then((katex) => drawFormula(katex, dom, tex, displayed))
      .catch(() => undefined);
    return { dom };
  };
}

function formula(name: "mathInline" | "mathBlock", displayed: boolean) {
  const tag = displayed ? "div" : "span";
  return Node.create({
    name,
    group: displayed ? "block" : "inline",
    inline: !displayed,
    atom: true,
    selectable: true,
    addAttributes() {
      return {
        tex: {
          default: "",
          parseHTML: (element: HTMLElement) => element.getAttribute("data-math") ?? "",
          renderHTML: (attributes: Record<string, unknown>) => ({ "data-math": attributes.tex }),
        },
      };
    },
    parseHTML() {
      return [{ tag: `${tag}[data-math]` }];
    },
    renderHTML({ node, HTMLAttributes }) {
      // The TeX is also the element's text, so the formula still reads before (or without) KaTeX.
      return [tag, mergeAttributes(HTMLAttributes), String(node.attrs.tex ?? "")];
    },
    addNodeView() {
      return formulaView(displayed);
    },
  });
}

export const MathInline = formula("mathInline", false);
export const MathBlock = formula("mathBlock", true);

/** A table as the server keeps it: no colgroup and no width style. */
const PlainTable = Table.extend({
  renderHTML({ HTMLAttributes }) {
    return ["table", mergeAttributes(this.options.HTMLAttributes, HTMLAttributes), ["tbody", 0]];
  },
});

export function pageExtensions(): Extensions {
  return [
    StarterKit.configure({
      heading: { levels: [2, 3, 4] },
      strike: false,
      underline: false,
      horizontalRule: false,
      link: { openOnClick: false, autolink: true, protocols: ["mailto"], HTMLAttributes: { target: null, rel: "noopener noreferrer" } },
    }),
    Image.configure({ inline: false, allowBase64: false }),
    PlainTable.configure({ resizable: false }),
    TableRow,
    TableHeader,
    TableCell,
    MathInline,
    MathBlock,
  ];
}

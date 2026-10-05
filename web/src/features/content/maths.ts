/**
 * Maths in pages (item 2.12, ADR 0012: KaTeX). A page stores each formula as TeX in a `data-math` attribute,
 * `<span data-math>` in a line and `<div data-math>` on a line of its own, with the TeX as the element's text
 * so it still reads if drawing fails. KaTeX is loaded only when a page has maths, so other pages stay light.
 *
 * KaTeX draws into the element itself (DOM nodes styled through the CSS object model), never through an HTML
 * string, so the Content-Security-Policy's ban on inline styles holds; `trust: false` refuses \href, \url and
 * the other commands that could reach outside the formula.
 */

type Katex = (typeof import("katex"))["default"];

let loading: Promise<Katex> | null = null;

/** KaTeX and its stylesheet, fetched once and on first need. */
export function loadKatex(): Promise<Katex> {
  loading ??= Promise.all([import("katex"), import("katex/dist/katex.min.css")]).then(([module]) => module.default);
  return loading;
}

/** Draw one formula into an element; a formula KaTeX cannot read is shown as its TeX, marked as such. */
export function drawFormula(katex: Katex, element: HTMLElement, tex: string, displayed: boolean) {
  try {
    katex.render(tex, element, { displayMode: displayed, throwOnError: true, trust: false, strict: "ignore", output: "htmlAndMathml" });
    element.classList.remove("math-error");
  } catch {
    element.textContent = tex;
    element.classList.add("math-error");
  }
}

/** Draw every formula inside an element. Does nothing, and loads nothing, when it has none. */
export async function drawMaths(root: HTMLElement): Promise<void> {
  const formulas = Array.from(root.querySelectorAll<HTMLElement>("[data-math]"));
  if (formulas.length === 0) return;
  const katex = await loadKatex();
  for (const element of formulas) drawFormula(katex, element, element.getAttribute("data-math") ?? "", element.tagName === "DIV");
}

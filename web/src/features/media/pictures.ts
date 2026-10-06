/**
 * Pictures on a page in data-light mode (item 4.05): each is held back behind a button that says what it
 * shows and how big it is, and is fetched only when that button is pressed.
 */

import { sizeInWords } from "../../api/types-content";

const ITEM = /\/api\/v1\/content\/(\d+)\/download\//;

/** The page's HTML with every picture held back: no address to fetch until it is asked for. */
export function holdPictures(html: string, sizes: Record<number, number> = {}): string {
  if (!html.includes("<img")) return html;
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
  const root = doc.body.firstElementChild!;
  root.querySelectorAll("img[src]").forEach((img, index) => {
    const src = img.getAttribute("src")!;
    const size = sizes[Number(ITEM.exec(src)?.[1])];
    img.setAttribute("data-held-src", src);
    img.setAttribute("data-held", String(index));
    img.removeAttribute("src");
    img.setAttribute("hidden", "");
    const button = doc.createElement("button");
    button.setAttribute("type", "button");
    button.setAttribute("class", "secondary small-button held-picture");
    button.setAttribute("data-show", String(index));
    const alt = img.getAttribute("alt") || "a picture";
    button.textContent = `Show picture: ${alt}${size ? ` (${sizeInWords(size)})` : ""}`;
    img.before(button);
  });
  return root.innerHTML;
}

/** Wire the buttons holdPictures made: pressing one fetches its picture and puts it in the button's place. */
export function wireHeldPictures(container: HTMLElement): () => void {
  const buttons = Array.from(container.querySelectorAll<HTMLButtonElement>("button[data-show]"));
  const show = (button: HTMLButtonElement) => () => {
    const img = container.querySelector<HTMLImageElement>(`img[data-held="${button.dataset.show}"]`);
    if (img) {
      img.src = img.dataset.heldSrc ?? "";
      img.hidden = false;
      img.tabIndex = -1;
      img.focus();
    }
    button.remove();
  };
  const handlers = buttons.map((button) => {
    const handler = show(button);
    button.addEventListener("click", handler);
    return () => button.removeEventListener("click", handler);
  });
  return () => handlers.forEach((off) => off());
}
